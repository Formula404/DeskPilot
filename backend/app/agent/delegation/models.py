from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.agent.manager.models import SpecialistName


class DelegationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    agent: SpecialistName
    objective: str
    depends_on: list[str] = Field(default_factory=list)
    input_refs: list[str] = Field(default_factory=list)
    expected_output: str
    status: Literal["pending", "running", "completed", "partial", "needs_input", "unsupported", "failed", "cancelled"] = "pending"
    result_refs: list[str] = Field(default_factory=list)
    result: dict[str, Any] | None = None

