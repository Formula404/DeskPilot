from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException

from backend.app.agent.graph import run_agent
from backend.app.api.events import event_bus
from backend.app.context.service import runtime_context_service
from backend.app.db.repository import (
    add_message,
    create_session,
    create_task,
    get_context_snapshot,
    get_session,
    get_task,
    list_task_steps,
    update_task,
)
from backend.app.schemas.tasks import ChatRequest, ChatResponse, TaskResponse

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    session_id = payload.session_id or create_session(source=payload.source)
    if not get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    snapshot_id = payload.context_snapshot_id
    if snapshot_id:
        snapshot = get_context_snapshot(snapshot_id)
        if not snapshot:
            raise HTTPException(status_code=404, detail="Context snapshot not found")
        if snapshot.get("session_id") and snapshot["session_id"] != session_id:
            raise HTTPException(status_code=409, detail="Context snapshot belongs to another session")
    elif payload.context_id:
        try:
            snapshot_id = runtime_context_service.create_legacy_snapshot(
                session_id=session_id, context_id=payload.context_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    turn_id = add_message(session_id, role="user", content=payload.message)
    task_id = create_task(
        payload.message,
        session_id=session_id,
        turn_id=turn_id,
        context_snapshot_id=snapshot_id,
    )
    await event_bus.publish("task.created", "任务已创建", task_id=task_id)
    asyncio.create_task(run_agent(task_id, payload.message, snapshot_id, event_bus))
    return ChatResponse(
        task_id=task_id,
        status="queued",
        session_id=session_id,
        context_snapshot_id=snapshot_id,
    )


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


@router.get("/tasks/{task_id}/trace")
def task_trace(task_id: str) -> dict:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    understanding = json.loads(task.get("intent_understanding_json") or "null")
    return {
        "task_id": task_id,
        "status": task["status"],
        "manager": {
            "model": task.get("manager_model"),
            "prompt_version": task.get("manager_prompt_version"),
            "schema_version": task.get("intent_schema_version"),
            "latency_ms": task.get("manager_latency_ms"),
            "fallback_reason": task.get("manager_fallback_reason"),
            "delegation_count": task.get("delegation_count") or 0,
        },
        "intent_understanding": understanding,
        "steps": list_task_steps(task_id),
    }


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict[str, bool]:
    update_task(task_id, status="cancelled")
    await event_bus.publish("task.cancelled", "任务已取消", task_id=task_id)
    return {"ok": True}
