from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class EventMessage(BaseModel):
    event_id: str
    task_id: str | None = None
    type: str
    message: str
    payload: dict[str, Any] = {}
    created_at: str
