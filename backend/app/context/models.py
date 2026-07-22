from __future__ import annotations

from typing import Any, TypedDict


class ContextBlock(TypedDict, total=False):
    id: str
    kind: str
    content: Any
    source: dict[str, Any]
    captured_at: str
    trust: str
    sensitivity: str
    relevance_score: float
    token_estimate: int
    truncated: bool
    expires_at: str | None
    required: bool


class ContextBundle(TypedDict, total=False):
    snapshot: dict[str, Any]
    conversation: dict[str, Any]
    preferences: list[ContextBlock]
    memories: list[ContextBlock]
    knowledge: list[ContextBlock]
    execution: dict[str, Any]
    provenance: list[dict[str, Any]]
    blocks: list[ContextBlock]
    budget: dict[str, Any]
    degraded_reasons: list[str]


INTENT_CONTEXT_POLICY: dict[str, set[str]] = {
    "web_page_summary": {"snapshot", "selection", "browser", "conversation", "preferences"},
    "web_table_export": {"snapshot", "browser", "conversation", "preferences", "artifacts"},
    "web_page_action": {"snapshot", "selection", "browser", "conversation", "preferences"},
    "knowledge_query": {"conversation", "preferences", "memories", "knowledge"},
    "knowledge_ingest": {"snapshot", "browser", "conversation"},
    "knowledge_maintenance": {"conversation", "preferences"},
    "knowledge_review": {"conversation"},
    "file_operation": {"conversation", "preferences", "artifacts"},
    "general_chat": {"conversation", "preferences", "memories", "artifacts"},
    "memory_write": {"conversation", "preferences"},
    "desktop_app_open": {"snapshot", "conversation", "preferences", "memories"},
}
