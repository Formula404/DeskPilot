from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Literal

from backend.app.db.connection import connect
from backend.app.db.repository import now_iso
from backend.app.knowledge.catalog import append_log, refresh_catalogs
from backend.app.knowledge.indexer import index_note_path, index_source_path, remove_from_index
from backend.app.knowledge.locking import KnowledgeLockBusy, knowledge_locks
from backend.app.knowledge.markdown import (
    atomic_write,
    parse_markdown_document,
    render_markdown_document,
    sha256_text,
)
from backend.app.knowledge.paths import from_knowledge_relative, knowledge_root, relative_to_knowledge
from backend.app.knowledge.repository import get_note, get_source, list_source_snapshots


class KnowledgeLifecycleError(RuntimeError):
    def __init__(self, message: str, code: str = "KNOWLEDGE_LIFECYCLE_FAILED") -> None:
        super().__init__(message)
        self.code = code


def _rewrite_status(path: Path, status: str) -> str:
    content = path.read_text(encoding="utf-8")
    metadata, body = parse_markdown_document(content)
    metadata["status"] = status
    rendered = render_markdown_document(metadata, body)
    atomic_write(path, rendered)
    return sha256_text(rendered)


def set_note_archived(note_id: str, archived: bool) -> dict[str, Any]:
    note = get_note(note_id)
    if not note:
        raise KnowledgeLifecycleError("知识页面不存在。", "KNOWLEDGE_NOTE_NOT_FOUND")
    status = "archived" if archived else "active"
    try:
        with knowledge_locks([f"note:{note_id}:write"]):
            digest = _rewrite_status(from_knowledge_relative(str(note["markdown_path"])), status)
            with connect() as connection:
                connection.execute(
                    "UPDATE knowledge_notes SET status=?, content_sha256=?, updated_at=? WHERE id=?",
                    (status, digest, now_iso(), note_id),
                )
            if archived:
                remove_from_index(note_id)
            else:
                index_note_path(from_knowledge_relative(str(note["markdown_path"])))
    except KnowledgeLockBusy as exc:
        raise KnowledgeLifecycleError(str(exc), exc.code) from exc
    refresh_catalogs()
    append_log("archive" if archived else "unarchive", str(note["title"]), note_id)
    return {"id": note_id, "status": status}


def trash_note(note_id: str) -> dict[str, Any]:
    note = get_note(note_id)
    if not note:
        raise KnowledgeLifecycleError("知识页面不存在。", "KNOWLEDGE_NOTE_NOT_FOUND")
    original = from_knowledge_relative(str(note["markdown_path"]))
    folder = knowledge_root() / "trash" / "notes" / note_id
    target = folder / original.name
    try:
        with knowledge_locks([f"note:{note_id}:write"]):
            folder.mkdir(parents=True, exist_ok=True)
            shutil.move(str(original), str(target))
            manifest = {
                "kind": "note",
                "id": note_id,
                "title": note["title"],
                "original_path": note["markdown_path"],
                "previous_status": note["status"],
                "trashed_at": now_iso(),
            }
            atomic_write(folder / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            with connect() as connection:
                connection.execute(
                    "UPDATE knowledge_notes SET status='trashed', previous_status=?, deleted_at=?, markdown_path=? WHERE id=?",
                    (note["status"], manifest["trashed_at"], relative_to_knowledge(target), note_id),
                )
                connection.execute("DELETE FROM knowledge_fts WHERE object_id=?", (note_id,))
                connection.execute(
                    "UPDATE knowledge_proposals SET status='rejected', resolved_at=? "
                    "WHERE target_note_id=? AND status='pending'",
                    (now_iso(), note_id),
                )
    except KnowledgeLockBusy as exc:
        raise KnowledgeLifecycleError(str(exc), exc.code) from exc
    refresh_catalogs()
    append_log("trash", str(note["title"]), f"Soft-deleted {note_id}")
    return {"id": note_id, "title": note["title"], "deleted": True, "recoverable": True}


def restore_note(note_id: str) -> dict[str, Any]:
    note = get_note(note_id, include_trashed=True)
    if not note or note.get("status") != "trashed":
        raise KnowledgeLifecycleError("回收站中没有该知识页面。", "KNOWLEDGE_TRASH_ITEM_NOT_FOUND")
    folder = knowledge_root() / "trash" / "notes" / note_id
    manifest_path = folder / "manifest.json"
    if not manifest_path.exists():
        raise KnowledgeLifecycleError("回收站清单已丢失。", "KNOWLEDGE_TRASH_MANIFEST_MISSING")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = from_knowledge_relative(str(note["markdown_path"]))
    target = from_knowledge_relative(str(manifest["original_path"]))
    with knowledge_locks([f"note:{note_id}:write"]):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        status = str(manifest.get("previous_status") or "active")
        with connect() as connection:
            connection.execute(
                "UPDATE knowledge_notes SET status=?, previous_status=NULL, deleted_at=NULL, markdown_path=? WHERE id=?",
                (status, relative_to_knowledge(target), note_id),
            )
        if status != "archived":
            index_note_path(target)
        shutil.rmtree(folder)
    refresh_catalogs()
    append_log("restore", str(note["title"]), f"Restored {note_id} from trash")
    return {"id": note_id, "status": status, "restored": True}


def set_source_archived(source_id: str, archived: bool) -> dict[str, Any]:
    source = get_source(source_id)
    if not source:
        raise KnowledgeLifecycleError("知识来源不存在。", "KNOWLEDGE_SOURCE_NOT_FOUND")
    status = "archived" if archived else "active"
    with knowledge_locks([f"source:{source_id}:write", f"source:{source_id}:compile"]):
        snapshots = list_source_snapshots(source_id)
        for snapshot in snapshots:
            path = from_knowledge_relative(str(snapshot["markdown_path"]))
            _rewrite_status(path, status)
            if archived:
                remove_from_index(str(snapshot["id"]))
            elif str(snapshot["id"]) == str(source.get("current_snapshot_id")):
                index_source_path(path)
        with connect() as connection:
            connection.execute(
                "UPDATE knowledge_sources SET status=?, updated_at=? WHERE id=?",
                (status, now_iso(), source_id),
            )
    append_log("archive" if archived else "unarchive", str(source.get("title")), source_id)
    return {"id": source_id, "status": status}


def trash_source(source_id: str) -> dict[str, Any]:
    source = get_source(source_id)
    if not source:
        raise KnowledgeLifecycleError("知识来源不存在。", "KNOWLEDGE_SOURCE_NOT_FOUND")
    folder = knowledge_root() / "trash" / "sources" / source_id
    mappings: list[dict[str, str]] = []
    with knowledge_locks([f"source:{source_id}:write", f"source:{source_id}:compile"]):
        folder.mkdir(parents=True, exist_ok=True)
        for snapshot in list_source_snapshots(source_id):
            original = from_knowledge_relative(str(snapshot["markdown_path"]))
            target = folder / f"{snapshot['id']}--{original.name}"
            shutil.move(str(original), str(target))
            mappings.append({"snapshot_id": str(snapshot["id"]), "original_path": str(snapshot["markdown_path"]), "trash_path": relative_to_knowledge(target)})
            remove_from_index(str(snapshot["id"]))
        manifest = {"kind": "source", "id": source_id, "title": source.get("title"), "previous_status": source["status"], "trashed_at": now_iso(), "snapshots": mappings}
        atomic_write(folder / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        with connect() as connection:
            for item in mappings:
                connection.execute("UPDATE knowledge_snapshots SET markdown_path=? WHERE id=?", (item["trash_path"], item["snapshot_id"]))
            connection.execute("UPDATE knowledge_sources SET status='trashed', previous_status=?, deleted_at=? WHERE id=?", (source["status"], manifest["trashed_at"], source_id))
    append_log("trash", str(source.get("title")), f"Soft-deleted source {source_id}")
    return {"id": source_id, "deleted": True, "recoverable": True}


def restore_source(source_id: str) -> dict[str, Any]:
    source = get_source(source_id, include_trashed=True)
    if not source or source.get("status") != "trashed":
        raise KnowledgeLifecycleError("回收站中没有该来源。", "KNOWLEDGE_TRASH_ITEM_NOT_FOUND")
    folder = knowledge_root() / "trash" / "sources" / source_id
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    status = str(manifest.get("previous_status") or "active")
    with knowledge_locks([f"source:{source_id}:write", f"source:{source_id}:compile"]):
        restored_current: Path | None = None
        with connect() as connection:
            for item in manifest["snapshots"]:
                source_path = from_knowledge_relative(item["trash_path"])
                target = from_knowledge_relative(item["original_path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source_path), str(target))
                connection.execute("UPDATE knowledge_snapshots SET markdown_path=? WHERE id=?", (item["original_path"], item["snapshot_id"]))
                if status != "archived" and item["snapshot_id"] == source.get("current_snapshot_id"):
                    restored_current = target
            connection.execute("UPDATE knowledge_sources SET status=?, previous_status=NULL, deleted_at=NULL WHERE id=?", (status, source_id))
        if restored_current:
            index_source_path(restored_current)
        shutil.rmtree(folder)
    append_log("restore", str(source.get("title")), f"Restored source {source_id}")
    return {"id": source_id, "status": status, "restored": True}


def list_trash() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    root = knowledge_root() / "trash"
    for path in root.glob("*/*/manifest.json"):
        try:
            items.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(items, key=lambda item: str(item.get("trashed_at", "")), reverse=True)
