from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import StreamingResponse

from backend.app.api.events import event_bus

router = APIRouter(tags=["events"])


@router.get("/events")
async def events(task_id: str | None = None) -> StreamingResponse:
    return StreamingResponse(
        event_bus.subscribe(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
