from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    task_id: str
    user_input: str
    context_id: str | None
    intent: str
    plan: list[str]
    observations: list[dict[str, Any]]
    step_count: int
    final_response: str
    artifacts: list[dict[str, str]]
    error: str | None
    knowledge_refs: list[dict[str, Any]]
    knowledge_job_id: str | None
    proposal_ids: list[str]
    retrieval_trace: dict[str, Any]
    publish_step: Callable[[dict[str, Any]], Awaitable[None]]
