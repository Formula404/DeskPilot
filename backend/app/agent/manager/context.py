from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.context.models import ContextBundle


class ManagerContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_message: str
    recent_messages: list[dict[str, str]]
    conversation_summary: str | None
    snapshot_summary: dict[str, Any]
    recent_artifact_refs: list[dict[str, Any]]
    available_agents: list[str]
    capability_summary: dict[str, list[str]]
    user_preferences: list[dict[str, Any]]
    relevant_memories: list[dict[str, Any]] = Field(default_factory=list)


def build_manager_context(
    message: str,
    bundle: ContextBundle,
    *,
    available_agents: list[str],
    capability_summary: dict[str, list[str]],
) -> ManagerContext:
    snapshot = bundle.get("snapshot") or {}
    browser = snapshot.get("browser") or {}
    window = snapshot.get("window") or {}
    conversation = bundle.get("conversation") or {}
    recent_messages = [
        {"role": str(item.get("role") or ""), "content": str(item.get("content") or "")[:2000]}
        for item in conversation.get("messages") or []
        if item.get("role") in {"user", "assistant"}
    ]
    selected_blocks = bundle.get("blocks") or []
    preferences = [
        dict(item.get("content") or {})
        for item in selected_blocks
        if item.get("kind") == "preference" and isinstance(item.get("content"), dict)
    ]
    memories = [
        {
            "reference_id": (item.get("source") or {}).get("id"),
            "content": str(item.get("content") or "")[:1000],
            "trust": item.get("trust"),
        }
        for item in selected_blocks
        if item.get("kind") == "memory" and item.get("content")
    ]
    snapshot_summary = {
        "snapshot_id": snapshot.get("id"),
        "captured_at": snapshot.get("captured_at"),
        "expired": "context_snapshot_expired" in (bundle.get("degraded_reasons") or []),
        "browser": {
            key: browser.get(key)
            for key in ("tab_id", "url", "title", "browser_context_id")
            if browser.get(key) is not None
        },
        "window": {
            key: window.get(key)
            for key in ("title", "process_name", "app_name", "window_id")
            if window.get(key) is not None
        },
        "has_selection": bool(snapshot.get("selection")),
        "attachment_count": len(snapshot.get("attachments") or []),
        "resolved_references": (bundle.get("execution") or {}).get("resolved_references") or {},
    }
    return ManagerContext(
        current_message=message,
        recent_messages=recent_messages,
        conversation_summary=str(conversation.get("summary") or "") or None,
        snapshot_summary=snapshot_summary,
        recent_artifact_refs=list((bundle.get("execution") or {}).get("recent_artifacts") or []),
        available_agents=available_agents,
        capability_summary=capability_summary,
        user_preferences=preferences,
        relevant_memories=memories,
    )
