from __future__ import annotations

import difflib
from typing import Any

from backend.app.knowledge.repository import get_note


def build_proposal_diff(proposal: dict[str, Any], payload: dict[str, Any] | None, target_note: dict[str, Any] | None) -> dict[str, Any]:
    operation = (payload or {}).get("operation") or {}
    current_sections = (target_note or {}).get("sections") or {}
    before = {
        "title": (target_note or {}).get("title") or "",
        "entity_type": (target_note or {}).get("entity_type") or "",
        "summary": current_sections.get("Summary", ""),
        "overview": current_sections.get("Overview", ""),
        "details": current_sections.get("Details", ""),
        "tags": ((target_note or {}).get("frontmatter") or {}).get("tags", []),
    }
    after = {
        "title": operation.get("title", ""),
        "entity_type": operation.get("entity_type", ""),
        "summary": operation.get("summary", ""),
        "overview": operation.get("overview", ""),
        "details": operation.get("details_markdown", ""),
        "tags": operation.get("tags", []),
    }
    fields = [
        {"field": key, "before": before[key], "after": after[key], "changed": before[key] != after[key]}
        for key in before
    ]
    markdown_before = "\n\n".join(str(before[key]) for key in ("summary", "overview", "details"))
    markdown_after = "\n\n".join(str(after[key]) for key in ("summary", "overview", "details"))
    lines = list(difflib.unified_diff(markdown_before.splitlines(), markdown_after.splitlines(), fromfile="current", tofile="proposal", lineterm=""))
    current_evidence = {tuple(str(value or "") for value in (item.get("source_id"), item.get("snapshot_id"), item.get("evidence_anchor"))) for item in (target_note or {}).get("sources", [])}
    proposed_evidence = {tuple(str(value or "") for value in (item.get("source_id"), item.get("snapshot_id"), item.get("anchor"))) for item in operation.get("evidence", [])}
    current_relations = {tuple(str(value or "") for value in (item.get("relation_type"), item.get("to_note_id"))) for item in (target_note or {}).get("relations", [])}
    proposed_relations = {tuple(str(value or "") for value in (item.get("relation_type"), item.get("target_note_id"))) for item in operation.get("relations", [])}
    current_hash = (target_note or {}).get("content_sha256")
    base_hash = proposal.get("base_note_sha256") or (payload or {}).get("base_note_sha256")
    return {
        "fields": fields,
        "unified_diff": lines,
        "evidence": {"added": sorted(proposed_evidence - current_evidence), "removed": sorted(current_evidence - proposed_evidence)},
        "relations": {"added": sorted(proposed_relations - current_relations), "removed": sorted(current_relations - proposed_relations)},
        "base": {"expected_note_sha256": base_hash, "current_note_sha256": current_hash, "matches": not target_note or bool(base_hash and current_hash == base_hash), "snapshot_id": proposal.get("base_snapshot_id") or (payload or {}).get("base_snapshot_id")},
        "changed_fields": [item["field"] for item in fields if item["changed"]],
    }
