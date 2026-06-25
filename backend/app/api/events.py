from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from backend.app.db.repository import new_id, now_iso
from backend.app.schemas.events import EventMessage


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[EventMessage]] = set()

    async def publish(
        self,
        event_type: str,
        message: str,
        *,
        task_id: str | None = None,
        payload: dict | None = None,
    ) -> None:
        event = EventMessage(
            event_id=new_id(),
            task_id=task_id,
            type=event_type,
            message=message,
            payload=payload or {},
            created_at=now_iso(),
        )
        for queue in list(self._subscribers):
            await queue.put(event)

    async def subscribe(self) -> AsyncIterator[str]:
        queue: asyncio.Queue[EventMessage] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                event = await queue.get()
                yield f"event: {event.type}\ndata: {json.dumps(event.model_dump(), ensure_ascii=False)}\n\n"
        finally:
            self._subscribers.discard(queue)


event_bus = EventBus()
