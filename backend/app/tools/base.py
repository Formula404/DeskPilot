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
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    output_schema: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }
    risk_level: str
    required_permissions: list[str]
    handler: ToolHandler

    @property
    def openai_name(self) -> str:
        return self.name.replace(".", "_")

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.openai_name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }
