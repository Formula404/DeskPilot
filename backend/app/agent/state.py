from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    task_id: str
    session_id: str
    turn_id: str
    user_input: str
    context_id: str | None
    context_snapshot_id: str | None
    context: dict[str, Any]
    intent: str
    manager_context: dict[str, Any]
    manager_plan: dict[str, Any]
    manager_metadata: dict[str, Any]
    manager_turn_count: int
    intent_understanding: dict[str, Any]
    delegations: list[dict[str, Any]]
    active_delegation_id: str | None
    unresolved_goals: list[str]
    plan: list[str]
    observations: list[dict[str, Any]]
    step_count: int
    final_response: str
    artifacts: list[dict[str, str]]
    error: str | None
    cancelled: bool
    knowledge_refs: list[dict[str, Any]]
    knowledge_job_id: str | None
    proposal_ids: list[str]
    retrieval_trace: dict[str, Any]
    publish_step: Callable[[dict[str, Any]], Awaitable[None]]
