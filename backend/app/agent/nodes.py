from __future__ import annotations

import re

from openai import AsyncOpenAI

from backend.app.agent.intents import detect_intent
from backend.app.agent.state import AgentState
from backend.app.agent.tool_calling import (
    ToolCallingError,
    run_web_page_summary_tool_agent,
    run_web_table_export_tool_agent,
)
from backend.app.core.config import get_settings
from backend.app.db.repository import add_task_step, update_task
from backend.app.schemas.common import ToolResult
from backend.app.tools.registry import tool_registry


def _next_step_index(state: AgentState) -> int:
    return int(state.get("step_count") or 0) + 1


async def _publish_step(state: AgentState, step: dict) -> None:
    publish_step = state.get("publish_step")
    if publish_step:
        await publish_step(step)


async def route_intent(state: AgentState) -> AgentState:
    intent = detect_intent(state["user_input"])
    step_index = _next_step_index(state)
    update_task(state["task_id"], intent=intent, status="running")
    add_task_step(
        state["task_id"],
        step_index=step_index,
        step_type="agent",
        name="intent_router",
        status="completed",
        input_data={"message": state["user_input"]},
        output_data={"intent": intent},
    )
    await _publish_step(
        state,
        {
            "step_index": step_index,
            "type": "agent",
            "name": "intent_router",
            "status": "completed",
            "input": {"message": state["user_input"]},
            "output": {"intent": intent},
        },
    )
    return {**state, "intent": intent, "step_count": step_index}


async def summarize_current_page(state: AgentState) -> AgentState:
    try:
        kwargs = {"task_id": state["task_id"], "user_input": state["user_input"]}
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
    result = await tool_registry.call(tool_name, payload)
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
            "final_response": "未配置 API Key，无法进行对话。请在 .env 中设置 OPENAI_API_KEY。",
            "error": "未配置 API Key，无法进行对话。请在 .env 中设置 OPENAI_API_KEY。",
        }

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or "https://api.openai.com/v1",
    )
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是 DeskPilot，一个个人桌面助手。"
                    "请用中文简洁、友好地回答用户的问题。"
                    "如果用户的问题不明确，可以追问。"
                ),
            },
            {"role": "user", "content": state["user_input"]},
        ],
    )
    return {
        **state,
        "final_response": response.choices[0].message.content or "",
    }


async def finalize(state: AgentState) -> AgentState:
    step_index = _next_step_index(state)
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
        return state
    update_task(
        state["task_id"],
        status="completed",
        result_summary=state.get("final_response", ""),
    )
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
    return state
