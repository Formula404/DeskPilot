from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    source: str = "floating_window"
    session_id: str | None = None
    context_snapshot_id: str | None = None
    context_id: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    task_id: str
    status: str
    session_id: str
    context_snapshot_id: str | None = None


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
    dom_summary: list[dict[str, Any]] = Field(default_factory=list)
    captured_at: str


class BrowserContextResponse(BaseModel):
    context_id: str
    ok: bool = True
