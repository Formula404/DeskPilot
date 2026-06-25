from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    source: str = "floating_window"
    context_id: str | None = None


class ChatResponse(BaseModel):
    task_id: str
    status: str


class TaskResponse(BaseModel):
    task_id: str
    status: str
    intent: str | None = None
    created_at: str
    updated_at: str
    result: Any = None
    error: dict[str, Any] | None = None


class BrowserContextRequest(BaseModel):
    tab_id: str | int | None = None
    url: str
    title: str | None = None
    visible_text: str = ""
    dom_summary: list[dict[str, Any]] = []
    captured_at: str


class BrowserContextResponse(BaseModel):
    context_id: str
    ok: bool = True
