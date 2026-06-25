from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import StreamingResponse

from backend.app.api.events import event_bus

router = APIRouter(tags=["events"])


@router.get("/events")
async def events() -> StreamingResponse:
    return StreamingResponse(event_bus.subscribe(), media_type="text/event-stream")
