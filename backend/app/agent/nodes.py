from __future__ import annotations

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
