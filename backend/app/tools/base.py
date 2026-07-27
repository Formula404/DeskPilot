from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.schemas.common import ToolResult


ToolHandler = Callable[[dict[str, Any]], Awaitable[ToolResult]]


class ToolDefinition(BaseModel):
    """Executable capability metadata owned by deterministic server code."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    domain: str | None = None
    description: str
    input_schema: dict[str, Any] = Field(default_factory=lambda: {
        "type": "object", "properties": {}, "additionalProperties": False
    })
    output_schema: dict[str, Any] = Field(default_factory=lambda: {
        "type": "object", "properties": {}, "additionalProperties": True
    })
    risk_level: str
    required_permissions: list[str]
    preconditions: list[str] = Field(default_factory=list)
    side_effects: list[str] = Field(default_factory=list)
    allowed_callers: list[str] = Field(default_factory=list)
    requires_confirmation: bool | None = None
    timeout_seconds: float = Field(default=30, gt=0, le=600)
    examples: list[str] = Field(default_factory=list)
    negative_examples: list[str] = Field(default_factory=list)
    handler: ToolHandler

    @model_validator(mode="after")
    def complete_capability_metadata(self) -> "ToolDefinition":
        prefix = self.name.split(".", 1)[0]
        if self.domain is None:
            self.domain = {"browser": "web"}.get(prefix, prefix)
        if not self.allowed_callers:
            self.allowed_callers = ["system", "api", f"{self.domain}_agent"]
        if self.requires_confirmation is None:
            self.requires_confirmation = self.risk_level in {"medium", "high"}
        if not self.preconditions:
            self.preconditions = [f"permission:{permission}" for permission in self.required_permissions]
        if not self.side_effects:
            self.side_effects = [
                f"uses:{permission}"
                for permission in self.required_permissions
                if any(action in permission for action in (":write", ":create", ":maintain", ":review"))
            ]
        return self

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

    def capability_summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "risk_level": self.risk_level,
            "preconditions": self.preconditions,
            "side_effects": self.side_effects,
            "requires_confirmation": self.requires_confirmation,
            "allowed_callers": self.allowed_callers,
            "examples": self.examples,
            "negative_examples": self.negative_examples,
        }


CapabilityDefinition = ToolDefinition
