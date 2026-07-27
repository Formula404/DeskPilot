from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.app.browser.bridge import BrowserBridgeError, browser_bridge
from backend.app.context.budget import ContextBudgeter, estimate_tokens
from backend.app.context.current_window import get_foreground_window
from backend.app.context.models import (
    AGENT_CONTEXT_POLICY,
    CAPABILITY_CONTEXT_REQUIREMENTS,
    ContextBlock,
    ContextBundle,
    INTENT_CONTEXT_POLICY,
)
from backend.app.context.security import contains_secret, redact_secrets
from backend.app.db.repository import (
    get_browser_context,
    get_context_snapshot,
    get_session,
    get_task,
    list_messages,
    list_preferences,
    list_recent_artifacts,
    list_session_tasks,
    new_id,
    now_iso,
    record_context_usage,
    save_context_snapshot,
    update_session,
)
from backend.app.knowledge.retrieval import search_knowledge
from backend.app.knowledge.settings import get_knowledge_settings
from backend.app.memory.search import retrieve_memory_refs
from backend.app.memory.repository import list_memories


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def snapshot_expired(snapshot: dict[str, Any], *, now: datetime | None = None) -> bool:
    expires_at = _parse_time(snapshot.get("expires_at"))
    return bool(expires_at and expires_at <= (now or datetime.now(UTC)))


def browser_target(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    browser = (snapshot or {}).get("browser") or {}
    tab_id = browser.get("tab_id")
    if tab_id is None:
        return None
    try:
        tab: str | int = int(tab_id)
    except (TypeError, ValueError):
        tab = str(tab_id)
    return {
        "tab": tab,
        "url": browser.get("url"),
        "document_id": browser.get("document_id"),
        "content_hash": browser.get("content_hash"),
    }


class RuntimeContextService:
    async def create_snapshot(
        self,
        *,
        session_id: str | None,
        source: str,
        include: list[str],
        attachments: list[dict[str, Any]] | None = None,
        sensitivity: str = "normal",
        ttl_seconds: int = 600,
    ) -> dict[str, Any]:
        if session_id and not get_session(session_id):
            raise ValueError("会话不存在。")
        captured = datetime.now(UTC)
        window: dict[str, Any] = {}
        browser: dict[str, Any] = {}
        selection: dict[str, Any] = {}
        degraded: list[str] = []
        if "window" in include:
            try:
                window = get_foreground_window() or {}
            except Exception as exc:
                degraded.append(f"window:{type(exc).__name__}")
        if "browser_metadata" in include or "selection" in include:
            try:
                metadata = await browser_bridge.collect_metadata()
                degraded.extend(
                    f"browser_metadata:{reason}"
                    for reason in metadata.get("_degraded_reasons") or []
                )
                browser = {
                    key: metadata.get(key)
                    for key in ("client_id", "tab_id", "url", "title", "document_id", "content_hash")
                    if metadata.get(key) is not None
                }
                if "selection" in include and metadata.get("selection_text"):
                    selection = {
                        "text": str(metadata["selection_text"])[:8000],
                        "selector_hint": metadata.get("selection_selector_hint"),
                    }
            except BrowserBridgeError as exc:
                degraded.append(f"browser:{exc}")
        if contains_secret(selection) or contains_secret(attachments or []):
            sensitivity = "secret"
        expires_at = (captured + timedelta(seconds=ttl_seconds)).isoformat()
        snapshot_id = save_context_snapshot(
            session_id=session_id,
            source=source,
            window=redact_secrets(window),
            browser=redact_secrets(browser),
            selection=redact_secrets(selection),
            attachments=redact_secrets(attachments or []),
            sensitivity=sensitivity,
            captured_at=captured.isoformat(),
            expires_at=expires_at,
        )
        return {
            "context_snapshot_id": snapshot_id,
            "captured_at": captured.isoformat(),
            "expires_at": expires_at,
            "available": {"window": bool(window), "browser": bool(browser), "selection": bool(selection)},
            "degraded_reasons": degraded,
        }

    def create_legacy_snapshot(
        self, *, session_id: str, context_id: str, source: str = "legacy_context_id"
    ) -> str:
        page = get_browser_context(context_id)
        if not page:
            raise ValueError("旧版 context_id 不存在。")
        captured = _parse_time(page.get("captured_at")) or datetime.now(UTC)
        return save_context_snapshot(
            session_id=session_id,
            source=source,
            window={},
            browser={
                "browser_context_id": context_id,
                "tab_id": page.get("tab_id"),
                "url": page.get("url"),
                "title": page.get("title"),
            },
            selection={},
            attachments=[],
            sensitivity="normal",
            captured_at=captured.isoformat(),
            expires_at=(datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
        )


class ConversationContextService:
    def load_window(self, session_id: str, *, max_tokens: int = 2000) -> dict[str, Any]:
        session = get_session(session_id) or {}
        messages = list_messages(session_id, limit=12)
        selected: list[dict[str, Any]] = []
        used = estimate_tokens(session.get("summary") or "")
        for message in reversed(messages):
            size = estimate_tokens(message.get("content") or "")
            if selected and used + size > max_tokens:
                break
            selected.append(message)
            used += size
        selected.reverse()
        return {"summary": session.get("summary") or "", "messages": selected, "token_estimate": used}

    def update_summary(self, session_id: str) -> None:
        messages = list_messages(session_id, limit=50)
        if len(messages) <= 12:
            return
        older = messages[:-8]
        user_goals = [item["content"][:240] for item in older if item["role"] == "user"][-5:]
        completed = [item["content"][:240] for item in older if item["role"] == "assistant"][-5:]
        summary = {
            "user_goals": user_goals,
            "constraints": [],
            "resolved_references": {},
            "completed": completed,
            "pending": [],
            "important_results": [],
            "preferences_observed": [],
        }
        update_session(
            session_id,
            summary=json.dumps(summary, ensure_ascii=False),
            summary_through_message_id=older[-1]["id"],
        )


def _block(
    kind: str,
    content: Any,
    *,
    source_type: str,
    source_id: str | None,
    captured_at: str | None = None,
    trust: str = "untrusted",
    sensitivity: str = "normal",
    relevance_score: float = 1.0,
    expires_at: str | None = None,
    required: bool = False,
) -> ContextBlock:
    return {
        "id": f"ctxblk_{new_id()}",
        "kind": kind,
        "content": content,
        "source": {"type": source_type, "id": source_id},
        "captured_at": captured_at or now_iso(),
        "trust": trust,
        "sensitivity": sensitivity,
        "relevance_score": relevance_score,
        "token_estimate": estimate_tokens(content),
        "truncated": False,
        "expires_at": expires_at,
        "required": required,
    }


class ContextBuilder:
    def __init__(self) -> None:
        self.budgeter = ContextBudgeter()
        self.conversation = ConversationContextService()

    async def build(
        self,
        *,
        task_id: str,
        intent: str | None = None,
        agent: str | None = None,
        capabilities: list[str] | None = None,
        token_budget: int = 9000,
    ) -> ContextBundle:
        task = get_task(task_id)
        if not task:
            raise ValueError("任务不存在。")
        if agent:
            policy = set(AGENT_CONTEXT_POLICY.get(agent, AGENT_CONTEXT_POLICY["conversation"]))
            capability_policy: set[str] = set()
            for capability in capabilities or []:
                requirements = CAPABILITY_CONTEXT_REQUIREMENTS.get(capability, set())
                policy.update(requirements)
                capability_policy.update(requirements)
            policy_key = f"agent:{agent}"
        else:
            legacy_intent = intent or "general_chat"
            policy = set(INTENT_CONTEXT_POLICY.get(legacy_intent, INTENT_CONTEXT_POLICY["general_chat"]))
            capability_policy = set()
            policy_key = f"legacy_intent:{legacy_intent}"
        snapshot_required = agent in {"manager", "web", "desktop"} or bool(
            intent and intent.startswith("web_")
        )
        browser_required = agent in {"manager", "web"} or "browser" in capability_policy or bool(
            intent and intent.startswith("web_")
        )
        snapshot = get_context_snapshot(task.get("context_snapshot_id")) if task.get("context_snapshot_id") else None
        degraded: list[str] = []
        if snapshot and snapshot_expired(snapshot):
            degraded.append("context_snapshot_expired")
        blocks: list[ContextBlock] = [
            _block(
                "user_message",
                task["user_message"],
                source_type="message",
                source_id=task.get("turn_id"),
                trust="user_provided",
                required=True,
            )
        ]
        if "snapshot" in policy and snapshot:
            blocks.append(
                _block(
                    "foreground_window",
                    snapshot.get("window") or {},
                    source_type="context_snapshot",
                    source_id=snapshot["id"],
                    captured_at=snapshot["captured_at"],
                    trust="user_provided",
                    sensitivity=snapshot["sensitivity"],
                    expires_at=snapshot.get("expires_at"),
                    required=snapshot_required,
                )
            )
        if "browser" in policy and snapshot and snapshot.get("browser"):
            blocks.append(
                _block(
                    "browser_page_metadata",
                    snapshot["browser"],
                    source_type="context_snapshot",
                    source_id=snapshot["id"],
                    captured_at=snapshot["captured_at"],
                    sensitivity=snapshot["sensitivity"],
                    expires_at=snapshot.get("expires_at"),
                    required=browser_required,
                )
            )
        if "selection" in policy and snapshot and snapshot.get("selection"):
            blocks.append(
                _block(
                    "selection",
                    snapshot["selection"],
                    source_type="context_snapshot",
                    source_id=snapshot["id"],
                    captured_at=snapshot["captured_at"],
                    trust="user_provided",
                    sensitivity=snapshot["sensitivity"],
                    relevance_score=1.0,
                    required=agent == "web",
                )
            )
        conversation: dict[str, Any] = {}
        if "conversation" in policy and task.get("session_id"):
            conversation = self.conversation.load_window(task["session_id"])
            for message in conversation["messages"]:
                if message["id"] == task.get("turn_id"):
                    continue
                blocks.append(
                    _block(
                        "conversation_summary" if message["role"] == "system_event" else "user_message",
                        {"role": message["role"], "content": message["content"]},
                        source_type="message",
                        source_id=message["id"],
                        captured_at=message["created_at"],
                        trust="user_provided" if message["role"] == "user" else "untrusted",
                        sensitivity=message["sensitivity"],
                        relevance_score=0.8,
                    )
                )
        preference_blocks: list[ContextBlock] = []
        if "preferences" in policy:
            for preference in list_preferences(5):
                preference_blocks.append(
                    _block(
                        "preference",
                        {"key": preference["key"], "value": preference["value"]},
                        source_type="user_preference",
                        source_id=preference["key"],
                        captured_at=preference["updated_at"],
                        trust="trusted",
                        relevance_score=0.75,
                    )
                )
            blocks.extend(preference_blocks)
        memory_blocks: list[ContextBlock] = []
        if "memories" in policy:
            try:
                memories = retrieve_memory_refs(task["user_message"])
                if agent == "manager":
                    seen_memory_ids = {item.get("id") for item in memories}
                    memories.extend(
                        item
                        for item in list_memories(10)
                        if item.get("id") not in seen_memory_ids and item.get("status") == "active"
                    )
            except Exception:
                memories = []
                degraded.append("memory_retrieval_failed")
            for memory in memories[:5]:
                if memory.get("sensitivity") == "secret" or contains_secret(memory.get("content") or ""):
                    continue
                memory_blocks.append(
                    _block(
                        "memory",
                        memory["content"],
                        source_type="memory_item",
                        source_id=memory["id"],
                        captured_at=memory["updated_at"],
                        trust="user_provided" if memory.get("source_type") == "user_explicit" else "untrusted",
                        sensitivity=memory["sensitivity"],
                        relevance_score=float(memory.get("confidence") or 0.5),
                        expires_at=memory.get("expires_at"),
                    )
                )
            blocks.extend(memory_blocks)
        knowledge_blocks: list[ContextBlock] = []
        if "knowledge" in policy:
            try:
                knowledge_settings = get_knowledge_settings()
                knowledge_results = (
                    search_knowledge(task["user_message"], 5)
                    if knowledge_settings.enabled
                    else []
                )
                for result in knowledge_results:
                    sources = [
                        {
                            "source_id": source.get("source_id"),
                            "snapshot_id": source.get("snapshot_id"),
                            "source_title": source.get("source_title"),
                            "canonical_uri": source.get("canonical_uri"),
                        }
                        for source in result.get("sources") or []
                    ]
                    sensitivities = {
                        str(source.get("sensitivity") or "normal")
                        for source in result.get("sources") or []
                    }
                    sensitivities.add(str(result.get("sensitivity") or "normal"))
                    sensitivity = (
                        "secret"
                        if "secret" in sensitivities
                        else "private"
                        if "private" in sensitivities
                        else "normal"
                    )
                    if sensitivity == "secret" or (
                        sensitivity == "private" and not knowledge_settings.allow_private_remote
                    ):
                        continue
                    evidence = {
                        "note_id": result.get("id"),
                        "title": result.get("title"),
                        "summary": result.get("summary"),
                        "overview": result.get("overview"),
                        "path": result.get("path"),
                        "status": result.get("status"),
                        "sources": sources,
                    }
                    if contains_secret(evidence):
                        continue
                    knowledge_blocks.append(
                        _block(
                            "knowledge_evidence",
                            evidence,
                            source_type="knowledge_note",
                            source_id=str(result.get("id") or ""),
                            captured_at=result.get("updated_at"),
                            trust="untrusted",
                            sensitivity=sensitivity,
                            relevance_score=0.85,
                        )
                    )
            except Exception:
                degraded.append("knowledge_retrieval_failed")
            blocks.extend(knowledge_blocks)
        artifacts: list[dict[str, Any]] = []
        if "artifacts" in policy and task.get("session_id"):
            artifacts = list_recent_artifacts(task["session_id"], 3)
            for artifact in artifacts:
                blocks.append(
                    _block(
                        "artifact_reference",
                        artifact,
                        source_type="task_step",
                        source_id=artifact.get("task_id"),
                        trust="trusted",
                        relevance_score=0.9,
                    )
                )
        resolved_references: dict[str, Any] = {}
        message_text = task["user_message"]
        if snapshot and snapshot.get("selection") and any(word in message_text for word in ("这个", "选中", "选区")):
            resolved_references["这个"] = {"type": "selection", "snapshot_id": snapshot["id"]}
        elif snapshot and snapshot.get("browser") and any(word in message_text for word in ("这个", "当前", "页面", "网页")):
            resolved_references["当前目标"] = {
                "type": "browser",
                "snapshot_id": snapshot["id"],
                "tab_id": snapshot["browser"].get("tab_id"),
            }
        if artifacts and any(word in message_text for word in ("它", "刚才那个", "刚才的文件", "那个文件")):
            resolved_references["它"] = {
                **artifacts[0],
                "artifact_type": artifacts[0].get("type"),
                "type": "artifact",
            }
        if task.get("session_id") and message_text.strip() in {"继续", "继续执行", "接着做"}:
            previous = [
                item
                for item in list_session_tasks(task["session_id"], limit=5)
                if item["id"] != task_id and item["status"] in {"queued", "running", "waiting_approval", "failed"}
            ]
            if previous:
                resolved_references["继续"] = {
                    "type": "task",
                    "task_id": previous[0]["id"],
                    "status": previous[0]["status"],
                    "goal": previous[0]["user_message"],
                }
        for reference, resolved in resolved_references.items():
            blocks.append(
                _block(
                    "artifact_reference" if resolved.get("type") == "artifact" else "task_reference",
                    {"reference": reference, "resolved": resolved},
                    source_type="reference_resolver",
                    source_id=str(resolved.get("task_id") or resolved.get("snapshot_id") or "current"),
                    trust="trusted",
                    relevance_score=1.0,
                )
            )
        selected, budget = self.budgeter.select(blocks, max_tokens=token_budget)
        record_context_usage(task_id, "build_context", selected)
        return {
            "snapshot": snapshot or {},
            "conversation": conversation,
            "preferences": preference_blocks,
            "memories": memory_blocks,
            "knowledge": [item for item in selected if item.get("kind") == "knowledge_evidence"],
            "execution": {
                "recent_artifacts": artifacts,
                "resolved_references": resolved_references,
                "context_policy": sorted(policy),
                "context_policy_key": policy_key,
                "intent_policy": sorted(policy),
            },
            "provenance": [
                {"block_id": item["id"], "kind": item["kind"], "source": item["source"]}
                for item in selected
            ],
            "blocks": selected,
            "budget": budget,
            "degraded_reasons": degraded,
        }


runtime_context_service = RuntimeContextService()
context_builder = ContextBuilder()


def render_context_for_model(bundle: ContextBundle, *, include_external: bool = True) -> str:
    blocks = []
    for block in bundle.get("blocks") or []:
        if block["kind"] == "user_message":
            continue
        if not include_external and block.get("trust") == "untrusted":
            continue
        blocks.append(
            {
                "id": block["id"],
                "kind": block["kind"],
                "content": block["content"],
                "source": block["source"],
                "trust": block["trust"],
                "sensitivity": block["sensitivity"],
                "truncated": block.get("truncated", False),
            }
        )
    return json.dumps({"context_blocks": blocks}, ensure_ascii=False)
