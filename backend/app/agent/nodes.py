from __future__ import annotations

from openai import AsyncOpenAI

from backend.app.agent.intents import detect_intent
from backend.app.agent.state import AgentState
from backend.app.core.config import get_settings
from backend.app.db.repository import add_task_step, update_task
from backend.app.tools.registry import tool_registry


async def route_intent(state: AgentState) -> AgentState:
    intent = detect_intent(state["user_input"])
    update_task(state["task_id"], intent=intent, status="running")
    add_task_step(
        state["task_id"],
        step_index=1,
        step_type="agent",
        name="intent_router",
        status="completed",
        input_data={"message": state["user_input"]},
        output_data={"intent": intent},
    )
    return {**state, "intent": intent}


async def summarize_current_page(state: AgentState) -> AgentState:
    browser_result = await tool_registry.call("browser.get_current_page", {})
    if not browser_result.ok:
        return {**state, "error": browser_result.message}

    summary_result = await tool_registry.call(
        "browser.summarize_current_page",
        {"page": browser_result.data, "instruction": state["user_input"]},
    )
    if not summary_result.ok:
        return {**state, "error": summary_result.message}

    write_result = await tool_registry.call(
        "file.write_markdown",
        {
            "title": browser_result.data.get("title") or "网页总结",
            "content": summary_result.data["summary"],
        },
    )
    if not write_result.ok:
        return {**state, "error": write_result.message}

    return {
        **state,
        "final_response": summary_result.data["summary"],
        "artifacts": [artifact.model_dump() for artifact in write_result.artifacts],
    }


async def general_chat(state: AgentState) -> AgentState:
    settings = get_settings()
    if not settings.openai_api_key:
        return {
            **state,
            "final_response": "未配置 API Key，无法进行对话。请在 .env 中设置 OPENAI_API_KEY。",
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
    if state.get("error"):
        update_task(
            state["task_id"],
            status="failed",
            error_code="AGENT_ERROR",
            error_message=state["error"],
        )
        return state
    update_task(
        state["task_id"],
        status="completed",
        result_summary=state.get("final_response", ""),
    )
    return state
