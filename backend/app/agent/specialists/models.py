from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WebAgentRequest(StrictRequest):
    objective: str
    snapshot_id: str
    selection_required: bool
    expected_output: str
    input_artifact_refs: list[str]


class KnowledgeAgentRequest(StrictRequest):
    objective: str
    source_refs: list[str]
    query: str | None
    proposal_id: str | None
    expected_output: str


class FileAgentRequest(StrictRequest):
    objective: str
    source_refs: list[str]
    target_format: str | None
    preferred_filename: str | None
    expected_output: str


class DesktopAgentRequest(StrictRequest):
    objective: str
    application_name: str | None
    target_window_id: str | None
    expected_output: str


class SpecialistAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "partial", "needs_input", "unsupported", "failed", "cancelled"]
    summary: str
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    unsupported_requirements: list[str] = Field(default_factory=list)
    suggested_next_actions: list[str] = Field(default_factory=list)

