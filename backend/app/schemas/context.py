from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    source: str = "floating_window"
    title: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    status: str = "active"


class SnapshotRequest(BaseModel):
    session_id: str | None = None
    source: str = "floating_window"
    include: list[Literal["window", "browser_metadata", "selection"]] = Field(
        default_factory=lambda: ["window", "browser_metadata", "selection"]
    )
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    sensitivity: Literal["normal", "personal", "sensitive", "secret"] = "normal"


class SnapshotResponse(BaseModel):
    context_snapshot_id: str
    captured_at: str
    expires_at: str | None
    available: dict[str, bool]
    degraded_reasons: list[str] = Field(default_factory=list)


class ContextBlockModel(BaseModel):
    id: str
    kind: str
    content: Any
    source: dict[str, Any]
    captured_at: str
    trust: str
    sensitivity: str
    relevance_score: float = 1.0
    token_estimate: int = 0
    truncated: bool = False
    expires_at: str | None = None

