from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict

from backend.app.schemas.common import ToolResult


ToolHandler = Callable[[dict[str, Any]], Awaitable[ToolResult]]


class ToolDefinition(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    risk_level: str
    required_permissions: list[str]
    handler: ToolHandler
