from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    task_id: str
    user_input: str
    context_id: str | None
    intent: str
    plan: list[str]
    observations: list[dict[str, Any]]
    final_response: str
    artifacts: list[dict[str, str]]
    error: str | None
