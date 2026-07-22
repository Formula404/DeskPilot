from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from backend.app.agent.nodes import (
    build_context,
    export_current_page_table,
    finalize,
    general_chat,
    ingest_knowledge,
    maintain_knowledge,
    query_knowledge,
    propose_or_write_memory,
    prepare_memory_write,
    review_knowledge,
    load_snapshot,
    load_task,
    route_intent,
    summarize_current_page,
)
from backend.app.agent.state import AgentState
from backend.app.api.events import EventBus
from backend.app.db.repository import get_task, update_task

logger = logging.getLogger(__name__)


def _route_after_intent(state: AgentState) -> str:
    if state.get("error"):
        return "finalize"
    if state.get("intent") == "knowledge_ingest":
        return "ingest_knowledge"
    if state.get("intent") == "knowledge_query":
        return "query_knowledge"
    if state.get("intent") == "knowledge_maintenance":
        return "maintain_knowledge"
    if state.get("intent") == "knowledge_review":
        return "review_knowledge"
    if state.get("intent") == "memory_write":
        return "prepare_memory_write"
    if state.get("intent") == "web_page_summary":
        return "summarize_current_page"
    if state.get("intent") == "web_table_export":
        return "export_current_page_table"
    return "general_chat"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("load_task", load_task)
    graph.add_node("load_snapshot", load_snapshot)
    graph.add_node("route_intent", route_intent)
    graph.add_node("build_context", build_context)
    graph.add_node("summarize_current_page", summarize_current_page)
    graph.add_node("export_current_page_table", export_current_page_table)
    graph.add_node("general_chat", general_chat)
    graph.add_node("ingest_knowledge", ingest_knowledge)
    graph.add_node("query_knowledge", query_knowledge)
    graph.add_node("maintain_knowledge", maintain_knowledge)
    graph.add_node("review_knowledge", review_knowledge)
    graph.add_node("prepare_memory_write", prepare_memory_write)
    graph.add_node("finalize", finalize)
    graph.add_node("propose_or_write_memory", propose_or_write_memory)
    graph.set_entry_point("load_task")
    graph.add_edge("load_task", "load_snapshot")
    graph.add_edge("load_snapshot", "route_intent")
    graph.add_edge("route_intent", "build_context")
    graph.add_conditional_edges(
        "build_context",
        _route_after_intent,
        {
            "finalize": "finalize",
            "summarize_current_page": "summarize_current_page",
            "export_current_page_table": "export_current_page_table",
            "general_chat": "general_chat",
            "ingest_knowledge": "ingest_knowledge",
            "query_knowledge": "query_knowledge",
            "maintain_knowledge": "maintain_knowledge",
            "review_knowledge": "review_knowledge",
            "prepare_memory_write": "prepare_memory_write",
        },
    )
    graph.add_edge("summarize_current_page", "finalize")
    graph.add_edge("export_current_page_table", "finalize")
    graph.add_edge("general_chat", "finalize")
    graph.add_edge("ingest_knowledge", "finalize")
    graph.add_edge("query_knowledge", "finalize")
    graph.add_edge("maintain_knowledge", "finalize")
    graph.add_edge("review_knowledge", "finalize")
    graph.add_edge("prepare_memory_write", "finalize")
    graph.add_edge("finalize", "propose_or_write_memory")
    graph.add_edge("propose_or_write_memory", END)
    return graph.compile()


async def run_agent(
    task_id: str,
    message: str,
    context_id: str | None,
    event_bus: EventBus,
) -> dict[str, Any]:
    async def publish_step(step: dict[str, Any]) -> None:
        name = step.get("name") or "unknown"
        step_type = step.get("type") or "agent"
        status = step.get("status") or "completed"
        event_type = (
            "task.step.started"
            if status in {"running", "started"}
            else "task.step.failed"
            if status == "failed"
            else "task.step.completed"
        )
        if name == "load_snapshot":
            message = "加载任务绑定的上下文快照"
            event_type = "context.loading"
        elif name == "build_context":
            message = "上下文已按任务意图装配"
            event_type = "context.ready"
        elif step_type == "tool":
            message = f"调用工具 {name}"
        elif name == "intent_router":
            message = "识别任务意图"
        elif name == "finalize":
            message = "生成任务结果"
        else:
            message = "执行步骤完成"
        await event_bus.publish(event_type, message, task_id=task_id, payload={"step": step})

    await event_bus.publish("task.started", "任务开始执行", task_id=task_id)
    update_task(task_id, status="running")
    try:
        result = await build_graph().ainvoke(
            {
                "task_id": task_id,
                "user_input": message,
                "context_id": context_id,
                "context_snapshot_id": context_id,
                "observations": [],
                "artifacts": [],
                "publish_step": publish_step,
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

    current_task = get_task(task_id)
    if result.get("cancelled") or (current_task and current_task.get("status") == "cancelled"):
        await event_bus.publish("task.cancelled", "任务已取消", task_id=task_id)
    elif result.get("error"):
        await event_bus.publish("task.failed", result["error"], task_id=task_id)
    else:
        await event_bus.publish(
            "task.completed",
            "任务已完成",
            task_id=task_id,
            payload={"artifacts": result.get("artifacts", [])},
        )
    return result
