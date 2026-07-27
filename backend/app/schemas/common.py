from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Artifact(BaseModel):
    type: str
    path: str


class ToolError(BaseModel):
    code: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    message: str = ""
    artifacts: list[Artifact] = Field(default_factory=list)
    error: ToolError | None = None
