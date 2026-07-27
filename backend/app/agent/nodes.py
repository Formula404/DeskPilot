from __future__ import annotations

import re

from openai import AsyncOpenAI

from backend.app.agent.state import AgentState
from backend.app.agent.tool_calling import (
    ToolCallingError,
    run_web_page_summary_tool_agent,
    run_web_table_export_tool_agent,
)
from backend.app.context.security import EXTERNAL_DATA_RULE, contains_secret
from backend.app.context.runtime_binding import bind_browser_target, reset_browser_target
from backend.app.context.service import (
    browser_target,
    context_builder,
    render_context_for_model,
    snapshot_expired,
)
from backend.app.settings.service import get_runtime_settings as get_settings
from backend.app.db.repository import (
    add_message,
    add_task_step,
    get_context_snapshot,
    get_task,
    record_context_usage,
    save_task_checkpoint,
    update_task,
)
from backend.app.context.budget import estimate_tokens
from backend.app.db.repository import new_id, now_iso
from backend.app.memory.repository import save_memory
from backend.app.schemas.common import ToolResult
from backend.app.tools.registry import tool_registry


def _next_step_index(state: AgentState) -> int:
    return int(state.get("step_count") or 0) + 1


async def load_task(state: AgentState) -> AgentState:
    task = get_task(state["task_id"])
    if not task:
        return {**state, "error": "任务不存在，无法恢复上下文。"}
    return {
        **state,
        "session_id": task.get("session_id") or "",
        "turn_id": task.get("turn_id") or "",
        "context_snapshot_id": task.get("context_snapshot_id"),
        "context_id": task.get("context_snapshot_id"),
    }


async def load_snapshot(state: AgentState) -> AgentState:
    snapshot_id = state.get("context_snapshot_id")
    snapshot = get_context_snapshot(snapshot_id) if snapshot_id else None
    if snapshot_id and not snapshot:
        return {**state, "error": "任务绑定的上下文快照不存在。"}
    step_index = _next_step_index(state)
    snapshot_output = {
        "context_snapshot_id": snapshot_id,
        "expired": snapshot_expired(snapshot) if snapshot else False,
        "target": (snapshot or {}).get("browser") or {},
    }
    add_task_step(
        state["task_id"],
        step_index=step_index,
        step_type="context",
        name="load_snapshot",
        status="completed",
        output_data=snapshot_output,
    )
    await _publish_step(
        state,
        {
            "step_index": step_index,
            "type": "context",
            "name": "load_snapshot",
            "status": "completed",
            "output": snapshot_output,
        },
    )
    return {**state, "context": {"snapshot": snapshot or {}}, "step_count": step_index}


async def _publish_step(state: AgentState, step: dict) -> None:
    publish_step = state.get("publish_step")
    if publish_step:
        await publish_step(step)


async def build_context(state: AgentState) -> AgentState:
    if state.get("error"):
        return state
    try:
        bundle = await context_builder.build(
            task_id=state["task_id"], intent=state["intent"], token_budget=9000
        )
    except Exception as exc:
        return {**state, "error": f"上下文装配失败：{exc}"}
    if state["intent"].startswith("web_") and not (bundle.get("snapshot") or {}).get("browser"):
        return {
            **state,
            "context": bundle,
            "error": "提交任务时没有绑定可用的浏览器标签页，不能改用执行时的其他页面。请重新打开目标页面后提交。",
        }
    step_index = _next_step_index(state)
    output = {
        "block_ids": [item["id"] for item in bundle.get("blocks") or []],
        "block_kinds": [item["kind"] for item in bundle.get("blocks") or []],
        "budget": bundle.get("budget"),
        "degraded_reasons": bundle.get("degraded_reasons"),
    }
    add_task_step(
        state["task_id"],
        step_index=step_index,
        step_type="context",
        name="build_context",
        status="completed",
        input_data={"intent": state["intent"], "token_budget": 9000},
        output_data=output,
    )
    await _publish_step(
        state,
        {
            "step_index": step_index,
            "type": "context",
            "name": "build_context",
            "status": "completed",
            "output": {"budget": bundle.get("budget"), "sources": len(bundle.get("provenance") or [])},
        },
    )
    next_state = {**state, "context": bundle, "step_count": step_index}
    save_task_checkpoint(state["task_id"], "build_context", next_state)
    return next_state


async def summarize_current_page(state: AgentState) -> AgentState:
    try:
        kwargs = {"task_id": state["task_id"], "user_input": state["user_input"]}
        if state.get("context"):
            kwargs["context_bundle"] = state["context"]
        if "step_count" in state:
            kwargs["start_step_index"] = int(state.get("step_count") or 0)
        if state.get("publish_step"):
            kwargs["on_step_recorded"] = lambda step: _publish_step(state, step)
        result = await run_web_page_summary_tool_agent(**kwargs)
    except ToolCallingError as exc:
        return {**state, "error": str(exc)}

    return {**state, **result}


async def export_current_page_table(state: AgentState) -> AgentState:
    try:
        kwargs = {"task_id": state["task_id"], "user_input": state["user_input"]}
        if state.get("context"):
            kwargs["context_bundle"] = state["context"]
        if "step_count" in state:
            kwargs["start_step_index"] = int(state.get("step_count") or 0)
        if state.get("publish_step"):
            kwargs["on_step_recorded"] = lambda step: _publish_step(state, step)
        result = await run_web_table_export_tool_agent(**kwargs)
    except ToolCallingError as exc:
        return {**state, "error": str(exc)}

    return {**state, **result}


async def _run_knowledge_tool(
    state: AgentState,
    tool_name: str,
    payload: dict,
) -> tuple[AgentState, ToolResult]:
    step_index = _next_step_index(state)
    binding_token = bind_browser_target(browser_target((state.get("context") or {}).get("snapshot")))
    try:
        result = await tool_registry.call(tool_name, payload)
    finally:
        reset_browser_target(binding_token)
    output = {
        "ok": result.ok,
        "message": result.message,
        "data": result.data,
        "error": result.error.model_dump() if result.error else None,
    }
    add_task_step(
        state["task_id"],
        step_index=step_index,
        step_type="tool",
        name=tool_name.replace(".", "_"),
        status="completed" if result.ok else "failed",
        input_data=payload,
        output_data=output,
    )
    await _publish_step(
        state,
        {
            "step_index": step_index,
            "type": "tool",
            "name": tool_name.replace(".", "_"),
            "status": "completed" if result.ok else "failed",
            "input": payload,
            "output": output,
        },
    )
    return {**state, "step_count": step_index}, result


async def ingest_knowledge(state: AgentState) -> AgentState:
    extensions = r"(?:md|txt|pdf|docx|png|jpe?g|webp|bmp|tiff?)"
    path_match = re.search(rf"[\"']([^\"']+\.{extensions})[\"']", state["user_input"], re.IGNORECASE)
    if not path_match:
        path_match = re.search(rf"([A-Za-z]:[\\/][^\n]+?\.{extensions})", state["user_input"], re.IGNORECASE)
    tool_name = "knowledge.ingest_file" if path_match else "knowledge.ingest_current_page"
    payload = {"path": path_match.group(1).strip()} if path_match else {}
    next_state, result = await _run_knowledge_tool(state, tool_name, payload)
    if not result.ok:
        return {**next_state, "error": result.message}
    data = result.data or {}
    compilation = data.get("compilation") or {}
    committed = compilation.get("committed") or []
    pending = compilation.get("pending") or []
    response = f"已将《{data.get('title') or '当前来源'}》加入知识库。"
    if data.get("status") == "already_exists":
        response = f"《{data.get('title') or '当前网页'}》已在知识库中，没有重复保存。"
    elif committed:
        response += f" 已生成 {len(committed)} 条知识条目。"
    if pending:
        response += f" 有 {len(pending)} 项更新等待审核。"
    return {
        **next_state,
        "final_response": response,
        "artifacts": [artifact.model_dump() for artifact in result.artifacts],
        "knowledge_refs": committed,
        "knowledge_job_id": compilation.get("job_id"),
        "proposal_ids": [item["proposal_id"] for item in pending],
    }


def _knowledge_query_text(message: str) -> str:
    cleaned = re.sub(
        r"^(请|帮我|麻烦)?\s*(在|从|用|根据)?\s*(我的)?\s*(知识库(?:里|中)?|资料里?)\s*(查一下|查询|搜索|回答)?[：:，,\s]*",
        "",
        message.strip(),
    )
    return cleaned or message.strip()


async def query_knowledge(state: AgentState) -> AgentState:
    query = _knowledge_query_text(state["user_input"])
    next_state, result = await _run_knowledge_tool(state, "knowledge.answer", {"query": query})
    if not result.ok:
        return {**next_state, "error": result.message}
    data = result.data or {}
    evidence_blocks = []
    for item in (data.get("results") or [])[:10]:
        content = item.get("summary") or item.get("overview") or item.get("title") or ""
        evidence_blocks.append(
            {
                "id": f"ctxblk_{new_id()}",
                "kind": "knowledge_evidence",
                "content": content,
                "source": {"type": "knowledge_note", "id": item.get("id")},
                "captured_at": item.get("updated_at") or now_iso(),
                "trust": "untrusted",
                "sensitivity": item.get("sensitivity") or "normal",
                "relevance_score": float(item.get("score") or 0.8),
                "token_estimate": estimate_tokens(content),
                "truncated": False,
            }
        )
    if evidence_blocks:
        record_context_usage(state["task_id"], "knowledge_retrieval", evidence_blocks)
    return {
        **next_state,
        "final_response": str(data.get("answer") or "知识库中没有足够材料。"),
        "knowledge_refs": data.get("results") or [],
        "retrieval_trace": {
            "query": query,
            "result_ids": [item.get("id") for item in data.get("results") or []],
            "model_used": data.get("model_used", False),
        },
    }


async def maintain_knowledge(state: AgentState) -> AgentState:
    message = state["user_input"]
    mentions_rebuild = "重建" in message
    asks_for_check = any(keyword in message for keyword in ["检查", "是否", "需不需要", "需要", "建议"])
    rebuild = mentions_rebuild and "确认" in message
    if mentions_rebuild and not asks_for_check and not rebuild:
        return {
            **state,
            "final_response": "重建索引会先备份数据库并重写派生索引。请明确回复“确认重建知识索引”后再执行。",
        }
    semantic = any(keyword in message for keyword in ["语义", "矛盾", "孤立页面", "知识空白"])
    tool_name = "knowledge.rebuild_index" if rebuild else "knowledge.semantic_lint" if semantic else "knowledge.lint"
    next_state, result = await _run_knowledge_tool(state, tool_name, {})
    if not result.ok:
        return {**next_state, "error": result.message}
    data = result.data or {}
    if rebuild:
        response = f"知识索引已重建：{data.get('notes', 0)} 条知识、{data.get('sources', 0)} 个来源。"
    elif semantic:
        summary = data.get("summary") or {}
        response = f"知识库语义检查完成：发现 {summary.get('issues', 0)} 项维护建议。"
    else:
        summary = data.get("summary") or {}
        response = (
            f"知识库检查完成：{summary.get('errors', 0)} 个错误，"
            f"{summary.get('warnings', 0)} 个警告。"
        )
    return {**next_state, "final_response": response}


async def review_knowledge(state: AgentState) -> AgentState:
    match = re.search(r"prop_[a-fA-F0-9]+", state["user_input"])
    if not match:
        return {**state, "final_response": "请提供要处理的知识提案 ID。"}
    message = state["user_input"]
    accept_requested = any(keyword in message for keyword in ["接受", "同意", "批准", "应用提案"])
    reject_requested = any(keyword in message for keyword in ["拒绝", "驳回"])
    if accept_requested == reject_requested:
        return {
            **state,
            "final_response": (
                f"提案 {match.group(0)} 尚未处理。"
                "请明确回复“接受提案 ID”或“拒绝提案 ID”。"
            ),
        }
    decision = "accept" if accept_requested else "reject"
    next_state, result = await _run_knowledge_tool(
        state,
        "knowledge.review_proposal",
        {"proposal_id": match.group(0), "decision": decision},
    )
    if not result.ok:
        return {**next_state, "error": result.message}
    action = "接受" if decision == "accept" else "拒绝"
    return {**next_state, "final_response": f"已{action}知识提案 {match.group(0)}。"}


async def general_chat(state: AgentState) -> AgentState:
    settings = get_settings()
    if not settings.openai_api_key:
        return {
            **state,
            "final_response": "未配置 API Key，无法进行对话。请在设置 → AI 设置中完成配置。",
            "error": "未配置 API Key，无法进行对话。请在设置 → AI 设置中完成配置。",
        }

    response_language = getattr(getattr(settings, "general", None), "response_language", "zh-CN")
    system_prompt = (
        "You are DeskPilot, a personal desktop assistant. Reply concisely and helpfully in English. "
        "Ask a clarifying question when the request is ambiguous."
        if response_language == "en"
        else "你是 DeskPilot，一个个人桌面助手。请用中文简洁、友好地回答用户的问题。如果用户的问题不明确，可以追问。"
    )
    system_prompt += "\n" + EXTERNAL_DATA_RULE
    conversation_messages = []
    for item in ((state.get("context") or {}).get("conversation") or {}).get("messages") or []:
        if item.get("id") == state.get("turn_id") or item.get("role") not in {"user", "assistant"}:
            continue
        conversation_messages.append({"role": item["role"], "content": item["content"]})
    context_payload = render_context_for_model(state.get("context") or {})
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=getattr(settings, "request_timeout_seconds", 60),
    )
    step_index = _next_step_index(state)
    step_input = {"message_count": len(conversation_messages) + 3, "model": settings.openai_model}
    await _publish_step(
        state,
        {
            "step_index": step_index,
            "type": "agent",
            "name": "general_chat_completion",
            "status": "running",
            "input": step_input,
        },
    )
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            temperature=getattr(settings, "temperature", 0.2),
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {"role": "system", "content": "以下是带来源和信任标记的上下文数据：\n" + context_payload},
                *conversation_messages,
                {"role": "user", "content": state["user_input"]},
            ],
        )
    except Exception as exc:
        add_task_step(
            state["task_id"],
            step_index=step_index,
            step_type="agent",
            name="general_chat_completion",
            status="failed",
            input_data=step_input,
            output_data={"error": str(exc)},
        )
        await _publish_step(
            state,
            {
                "step_index": step_index,
                "type": "agent",
                "name": "general_chat_completion",
                "status": "failed",
                "output": {"error": str(exc)},
            },
        )
        return {**state, "step_count": step_index, "error": f"通用对话请求失败：{exc}"}
    final_response = response.choices[0].message.content or ""
    add_task_step(
        state["task_id"],
        step_index=step_index,
        step_type="agent",
        name="general_chat_completion",
        status="completed",
        input_data=step_input,
        output_data={"final_response": final_response},
    )
    await _publish_step(
        state,
        {
            "step_index": step_index,
            "type": "agent",
            "name": "general_chat_completion",
            "status": "completed",
            "output": {"final_response": final_response},
        },
    )
    return {
        **state,
        "step_count": step_index,
        "final_response": final_response,
    }


async def prepare_memory_write(state: AgentState) -> AgentState:
    match = re.search(r"(?:请)?记住[：:,，\s]*(.+)", state.get("user_input", "").strip())
    content = match.group(1).strip() if match else ""
    if not content:
        return {**state, "final_response": "请告诉我要记住的具体内容。"}
    if contains_secret(content):
        return {**state, "final_response": "这段内容看起来包含密钥或认证信息，我不会把它写入长期记忆。"}
    return {**state, "final_response": "好的，我会按你的明确要求记住这项信息。"}


async def finalize(state: AgentState) -> AgentState:
    step_index = _next_step_index(state)
    task = get_task(state["task_id"])
    if state.get("cancelled") or (task and task.get("status") == "cancelled"):
        return {**state, "cancelled": True}
    if state.get("error"):
        update_task(
            state["task_id"],
            status="failed",
            error_code="AGENT_ERROR",
            error_message=state["error"],
        )
        await _publish_step(
            state,
            {
                "step_index": step_index,
                "type": "agent",
                "name": "finalize",
                "status": "failed",
                "output": {"error": state["error"]},
            },
        )
        save_task_checkpoint(state["task_id"], "finalize", state)
        return state
    update_task(
        state["task_id"],
        status="completed",
        result_summary=state.get("final_response", ""),
    )
    if state.get("session_id") and state.get("final_response"):
        add_message(
            state["session_id"],
            role="assistant",
            content=state.get("final_response", ""),
            task_id=state["task_id"],
            content_data={"artifacts": state.get("artifacts", [])},
        )
        context_builder.conversation.update_summary(state["session_id"])
    await _publish_step(
        state,
        {
            "step_index": step_index,
            "type": "agent",
            "name": "finalize",
            "status": "completed",
            "output": {
                "final_response": state.get("final_response", ""),
                "artifacts": state.get("artifacts", []),
            },
        },
    )
    save_task_checkpoint(state["task_id"], "finalize", state)
    return state


async def propose_or_write_memory(state: AgentState) -> AgentState:
    if state.get("error"):
        return state
    message = state.get("user_input", "").strip()
    match = re.search(r"(?:请)?记住[：:,，\s]*(.+)", message)
    if not match:
        return state
    content = match.group(1).strip()
    if not content:
        return state
    if contains_secret(content):
        step_index = _next_step_index(state)
        add_task_step(
            state["task_id"],
            step_index=step_index,
            step_type="memory",
            name="reject_secret_memory",
            status="completed",
            output_data={"written": False, "reason": "secret_detected"},
        )
        next_state = {**state, "step_count": step_index}
        save_task_checkpoint(state["task_id"], "reject_secret_memory", next_state)
        return next_state
    kind = "preference" if any(word in content for word in ("喜欢", "默认", "偏好", "习惯")) else "fact"
    try:
        memory_id = save_memory(
            kind=kind,
            content=content,
            source_task_id=state["task_id"],
            source_type="user_explicit",
        )
    except ValueError:
        return state
    step_index = _next_step_index(state)
    add_task_step(
        state["task_id"],
        step_index=step_index,
        step_type="memory",
        name="write_explicit_memory",
        status="completed",
        output_data={"memory_id": memory_id, "kind": kind},
    )
    next_state = {**state, "step_count": step_index}
    save_task_checkpoint(state["task_id"], "propose_or_write_memory", next_state)
    return next_state
