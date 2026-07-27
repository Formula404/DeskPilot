from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from backend.app.agent.manager.graph_nodes import (
    build_manager_context_node,
    execute_agent_tool_node,
    manager_node,
    route_manager,
)
from backend.app.agent.nodes import finalize, load_snapshot, load_task, propose_or_write_memory
from backend.app.agent.state import AgentState
from backend.app.api.events import EventBus
from backend.app.db.repository import get_task, update_task

logger = logging.getLogger(__name__)


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("load_task", load_task)
    graph.add_node("load_snapshot", load_snapshot)
    graph.add_node("build_manager_context", build_manager_context_node)
    graph.add_node("manager", manager_node)
    graph.add_node("execute_agent_tool", execute_agent_tool_node)
    graph.add_node("finalize", finalize)
    graph.add_node("memory_policy", propose_or_write_memory)
    graph.set_entry_point("load_task")
    graph.add_edge("load_task", "load_snapshot")
    graph.add_edge("load_snapshot", "build_manager_context")
    graph.add_edge("build_manager_context", "manager")
    graph.add_conditional_edges(
        "manager",
        route_manager,
        {
            "manager": "manager",
            "execute_agent_tool": "execute_agent_tool",
            "finalize": "finalize",
        },
    )
    graph.add_edge("execute_agent_tool", "manager")
    graph.add_edge("finalize", "memory_policy")
    graph.add_edge("memory_policy", END)
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
            event_type, user_message = "context.loading", "加载任务绑定的上下文快照"
        elif name == "build_manager_context":
            event_type, user_message = "context.ready", "Manager 上下文已装配"
        elif name == "manager.understand":
            user_message = "理解完整目标并生成委派计划"
        elif name == "manager.clarify":
            user_message = "需要补充任务信息"
        elif name.startswith("manager.delegate."):
            user_message = f"委派给 {name.rsplit('.', 1)[-1].title()} Agent"
        elif name == "manager.synthesize":
            user_message = "Manager 汇总专业 Agent 结果"
        elif step_type == "tool":
            user_message = f"调用工具 {name}"
        elif name == "finalize":
            user_message = "生成任务结果"
        else:
            user_message = "执行步骤完成"
        await event_bus.publish(event_type, user_message, task_id=task_id, payload={"step": step})

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
