from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.db.connection import connect
from backend.app.db.repository import now_iso
from backend.app.knowledge.catalog import append_log, refresh_catalogs
from backend.app.knowledge.indexer import index_note_path
from backend.app.knowledge.markdown import (
    atomic_write,
    parse_markdown_document,
    render_note,
    sha256_text,
    slugify,
    split_sections,
)
from backend.app.knowledge.models import EvidenceItem, NoteFrontmatter
from backend.app.knowledge.paths import from_knowledge_relative, knowledge_root, relative_to_knowledge
from backend.app.knowledge.repository import get_note, upsert_note


class KnowledgeNoteManagementError(RuntimeError):
    pass


def update_managed_note(note_id: str, values: dict[str, Any]) -> dict[str, Any]:
    note = get_note(note_id)
    if not note:
        raise KnowledgeNoteManagementError("知识页面不存在。")

    old_path = from_knowledge_relative(str(note["markdown_path"]))
    metadata, body = parse_markdown_document(old_path.read_text(encoding="utf-8"))
    old_frontmatter = NoteFrontmatter.model_validate(metadata)
    _, old_sections = split_sections(body)
    now = now_iso()
    entity_type = str(values["entity_type"])
    title = str(values["title"]).strip()
    frontmatter = old_frontmatter.model_copy(
        update={
            "entity_type": entity_type,
            "title": title,
            "tags": sorted({str(item).strip() for item in values.get("tags", []) if str(item).strip()}),
            "updated_at": now,
            "generated_by": "user",
            "review_state": "reviewed",
            "manual_sections": ["Summary", "Overview", "Details"],
        }
    )
    evidence = [
        EvidenceItem(
            source_id=str(item["source_id"]),
            snapshot_id=str(item["snapshot_id"]),
            anchor=str(item["evidence_anchor"]),
            reason="保留的来源证据",
        )
        for item in note.get("sources", [])
        if item.get("snapshot_id") and item.get("evidence_anchor")
    ]
    relation_lines = [
        f"`{item['relation_type']}` `{item['to_note_id']}`" for item in note.get("relations", [])
    ]
    rendered = render_note(
        frontmatter,
        summary=str(values.get("summary", old_sections.get("Summary", ""))),
        overview=str(values.get("overview", old_sections.get("Overview", ""))),
        details=str(values.get("details", old_sections.get("Details", ""))),
        evidence=evidence,
        relations=relation_lines,
    )
    new_path = knowledge_root() / "notes" / entity_type / f"{slugify(title)}--{note_id[-8:]}.md"
    atomic_write(new_path, rendered)
    upsert_note(
        note_id=note_id,
        entity_type=entity_type,
        title=title,
        markdown_path=relative_to_knowledge(new_path),
        status="active",
        review_state="reviewed",
        sensitivity=frontmatter.sensitivity,
        content_sha256=sha256_text(rendered),
        created_at=str(note["created_at"]),
        updated_at=now,
    )
    index_note_path(new_path)
    if old_path.resolve() != new_path.resolve():
        old_path.unlink(missing_ok=True)
    refresh_catalogs()
    append_log("edit", title, f"Manually edited knowledge page {note_id}.")
    return get_note(note_id) or {}


def delete_managed_note(note_id: str) -> dict[str, Any]:
    from backend.app.knowledge.lifecycle import KnowledgeLifecycleError, trash_note

    try:
        return trash_note(note_id)
    except KnowledgeLifecycleError as exc:
        raise KnowledgeNoteManagementError(str(exc)) from exc
