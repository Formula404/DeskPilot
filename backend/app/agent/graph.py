from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from backend.app.agent.nodes import finalize, general_chat, route_intent, summarize_current_page
from backend.app.agent.state import AgentState
from backend.app.api.events import EventBus
from backend.app.db.repository import update_task

logger = logging.getLogger(__name__)


def _route_after_intent(state: AgentState) -> str:
    if state.get("intent") == "web_page_summary":
        return "summarize_current_page"
    return "general_chat"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("route_intent", route_intent)
    graph.add_node("summarize_current_page", summarize_current_page)
    graph.add_node("general_chat", general_chat)
    graph.add_node("finalize", finalize)
    graph.set_entry_point("route_intent")
    graph.add_conditional_edges(
        "route_intent",
        _route_after_intent,
        {
            "summarize_current_page": "summarize_current_page",
            "general_chat": "general_chat",
        },
    )
    graph.add_edge("summarize_current_page", "finalize")
    graph.add_edge("general_chat", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


async def run_agent(
    task_id: str,
    message: str,
    context_id: str | None,
    event_bus: EventBus,
) -> dict[str, Any]:
    await event_bus.publish("task.started", "任务开始执行", task_id=task_id)
    update_task(task_id, status="running")
    try:
        result = await build_graph().ainvoke(
            {
                "task_id": task_id,
                "user_input": message,
                "context_id": context_id,
                "observations": [],
                "artifacts": [],
            }
        )
    except Exception as exc:
        logger.exception("Agent execution failed")
        update_task(
            task_id,
            status="failed",
            error_code="AGENT_EXCEPTION",
            error_message=str(exc),
        )
        await event_bus.publish("task.failed", str(exc), task_id=task_id)
        return {"error": str(exc)}

    if result.get("error"):
        await event_bus.publish("task.failed", result["error"], task_id=task_id)
    else:
        await event_bus.publish(
            "task.completed",
            "任务已完成",
            task_id=task_id,
            payload={"artifacts": result.get("artifacts", [])},
        )
    return result
