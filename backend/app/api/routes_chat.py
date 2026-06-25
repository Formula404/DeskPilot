from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from backend.app.agent.graph import run_agent
from backend.app.api.events import event_bus
from backend.app.db.repository import create_task, get_task, update_task
from backend.app.schemas.tasks import ChatRequest, ChatResponse, TaskResponse

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    task_id = create_task(payload.message)
    await event_bus.publish("task.created", "任务已创建", task_id=task_id)
    asyncio.create_task(run_agent(task_id, payload.message, payload.context_id, event_bus))
    return ChatResponse(task_id=task_id, status="queued")


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def task_detail(task_id: str) -> TaskResponse:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    error = None
    if task.get("error_code"):
        error = {"code": task["error_code"], "message": task.get("error_message")}
    return TaskResponse(
        task_id=task["id"],
        status=task["status"],
        intent=task.get("intent"),
        created_at=task["created_at"],
        updated_at=task["updated_at"],
        result=task.get("result_summary"),
        error=error,
    )


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict[str, bool]:
    update_task(task_id, status="cancelled")
    await event_bus.publish("task.cancelled", "任务已取消", task_id=task_id)
    return {"ok": True}
