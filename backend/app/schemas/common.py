from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Artifact(BaseModel):
    type: str
    path: str


class ToolError(BaseModel):
    code: str
    detail: dict[str, Any] = {}


class ToolResult(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    message: str = ""
    artifacts: list[Artifact] = []
    error: ToolError | None = None
