from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


DomainName = Literal["web", "knowledge", "file", "desktop", "conversation"]
SpecialistName = Literal["web", "knowledge", "file", "desktop"]
OperationClass = Literal[
    "read",
    "search",
    "extract",
    "transform",
    "create",
    "save",
    "update",
    "delete",
    "open",
    "communicate",
    "inspect",
    "approve",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TargetReference(StrictModel):
    kind: Literal[
        "current_browser_page",
        "browser_selection",
        "knowledge_base",
        "local_file",
        "artifact",
        "desktop_application",
        "conversation",
        "unknown",
    ]
    reference_id: str | None
    description: str


class UserConstraint(StrictModel):
    name: str
    value: str


class IntentUnderstanding(StrictModel):
    schema_version: int
    domains: list[DomainName]
    operation_classes: list[OperationClass]
    goal_summary: str
    targets: list[TargetReference]
    constraints: list[UserConstraint]
    needs_clarification: bool
    clarification_question: str | None
    unsupported_requirements: list[str]
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def clarification_is_consistent(self) -> "IntentUnderstanding":
        if self.needs_clarification and not (self.clarification_question or "").strip():
            raise ValueError("需要澄清时必须提供 clarification_question")
        if not self.needs_clarification and self.clarification_question is not None:
            raise ValueError("无需澄清时 clarification_question 必须为 null")
        return self


class PlannedDelegation(StrictModel):
    id: str = Field(pattern=r"^delegation_[A-Za-z0-9_-]+$")
    agent: SpecialistName
    objective: str = Field(min_length=1, max_length=1000)
    depends_on: list[str]
    input_refs: list[str]
    expected_output: str = Field(min_length=1, max_length=500)


class ManagerPlan(StrictModel):
    intent_understanding: IntentUnderstanding
    action: Literal["clarify", "respond", "delegate"]
    response: str | None
    delegations: list[PlannedDelegation]

    @model_validator(mode="after")
    def action_is_consistent(self) -> "ManagerPlan":
        if self.intent_understanding.needs_clarification and self.action != "clarify":
            raise ValueError("needs_clarification=true 时 action 必须为 clarify")
        if self.action == "clarify" and not (
            self.intent_understanding.clarification_question or self.response or ""
        ).strip():
            raise ValueError("clarify 必须包含一个问题")
        if self.action == "respond" and not (self.response or "").strip():
            raise ValueError("respond 必须包含 response")
        if self.action == "delegate" and not self.delegations:
            raise ValueError("delegate 必须包含至少一个委派")
        if self.action != "delegate" and self.delegations:
            raise ValueError("非 delegate 动作不能包含委派")
        return self


class ManagerFinalResponse(StrictModel):
    response: str = Field(min_length=1)

