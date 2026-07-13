from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from backend.app.db.connection import connect
from backend.app.knowledge.indexer import indexed_object_ids
from backend.app.knowledge.markdown import parse_markdown_document, sha256_text, source_chunks
from backend.app.knowledge.models import NoteFrontmatter, SourceFrontmatter
from backend.app.knowledge.paths import knowledge_root
from backend.app.knowledge.source_service import detect_secret


def _issue(level: str, code: str, message: str, path: Path | None = None) -> dict[str, str]:
    item = {"level": level, "code": code, "message": message}
    if path:
        item["path"] = path.resolve().relative_to(knowledge_root().resolve()).as_posix()
    return item


def lint_knowledge() -> dict[str, Any]:
    root = knowledge_root()
    issues: list[dict[str, str]] = []
    note_files: dict[str, tuple[Path, NoteFrontmatter, str]] = {}
    snapshot_files: dict[str, tuple[Path, SourceFrontmatter]] = {}
    titles: list[str] = []

    for path in (root / "sources").rglob("*.md"):
        try:
            content = path.read_text(encoding="utf-8")
            metadata, _ = parse_markdown_document(content)
            frontmatter = SourceFrontmatter.model_validate(metadata)
            if frontmatter.snapshot_id in snapshot_files:
                issues.append(_issue("error", "DUPLICATE_SNAPSHOT_ID", frontmatter.snapshot_id, path))
            snapshot_files[frontmatter.snapshot_id] = (path, frontmatter)
            if sha256_text("\n\n".join(source_chunks(content).values())) != frontmatter.content_sha256:
                issues.append(_issue("warning", "SOURCE_HASH_DRIFT", "来源正文哈希与 Frontmatter 不一致。", path))
            if detect_secret(content):
                issues.append(_issue("error", "SECRET_DETECTED", "文件包含疑似秘密信息。", path))
        except Exception as exc:
            issues.append(_issue("error", "SOURCE_SCHEMA_INVALID", str(exc), path))

    for path in (root / "notes").rglob("*.md"):
        try:
            content = path.read_text(encoding="utf-8")
            metadata, _ = parse_markdown_document(content)
            frontmatter = NoteFrontmatter.model_validate(metadata)
            if frontmatter.id in note_files:
                issues.append(_issue("error", "DUPLICATE_NOTE_ID", frontmatter.id, path))
            note_files[frontmatter.id] = (path, frontmatter, content)
            titles.append("".join(frontmatter.title.casefold().split()))
            if frontmatter.status == "active" and not frontmatter.source_ids:
                issues.append(_issue("warning", "ACTIVE_NOTE_WITHOUT_SOURCE", "active Note 没有来源。", path))
            if detect_secret(content):
                issues.append(_issue("error", "SECRET_DETECTED", "文件包含疑似秘密信息。", path))
        except Exception as exc:
            issues.append(_issue("error", "NOTE_SCHEMA_INVALID", str(exc), path))

    for title, count in Counter(titles).items():
        if count > 1:
            issues.append(_issue("warning", "DUPLICATE_NOTE_TITLE", f"重复规范化标题：{title}"))

    with connect() as connection:
        sources = {row["id"]: dict(row) for row in connection.execute("SELECT * FROM knowledge_sources")}
        snapshots = {
            row["id"]: dict(row) for row in connection.execute("SELECT * FROM knowledge_snapshots")
        }
        notes = {row["id"]: dict(row) for row in connection.execute("SELECT * FROM knowledge_notes")}
        links = [dict(row) for row in connection.execute("SELECT * FROM knowledge_note_sources")]
        relations = [dict(row) for row in connection.execute("SELECT * FROM knowledge_relations")]

    for snapshot_id, item in snapshots.items():
        if snapshot_id not in snapshot_files:
            issues.append(_issue("error", "SNAPSHOT_FILE_MISSING", f"快照文件缺失：{snapshot_id}"))
        if item["source_id"] not in sources:
            issues.append(_issue("error", "SNAPSHOT_SOURCE_MISSING", f"快照来源缺失：{snapshot_id}"))
    for snapshot_id, (path, _) in snapshot_files.items():
        if snapshot_id not in snapshots:
            issues.append(_issue("warning", "SNAPSHOT_INDEX_MISSING", "快照未登记到数据库。", path))
    for note_id, item in notes.items():
        if note_id not in note_files:
            issues.append(_issue("error", "NOTE_FILE_MISSING", f"Note 文件缺失：{note_id}"))
        elif sha256_text(note_files[note_id][2]) != item["content_sha256"]:
            issues.append(_issue("warning", "NOTE_HASH_DRIFT", f"Note 被外部修改：{note_id}"))
    for note_id, (path, _, _) in note_files.items():
        if note_id not in notes:
            issues.append(_issue("warning", "NOTE_INDEX_MISSING", "Note 未登记到数据库。", path))
    for link in links:
        if link["note_id"] not in notes or link["source_id"] not in sources:
            issues.append(_issue("error", "EVIDENCE_LINK_BROKEN", "Note 来源链接无效。"))
        snapshot_file = snapshot_files.get(str(link.get("snapshot_id")))
        if snapshot_file and link.get("evidence_anchor") not in source_chunks(
            snapshot_file[0].read_text(encoding="utf-8")
        ):
            issues.append(_issue("error", "EVIDENCE_ANCHOR_MISSING", "Evidence anchor 不存在。"))
    for relation in relations:
        if relation["from_note_id"] not in notes or relation["to_note_id"] not in notes:
            issues.append(_issue("error", "RELATION_BROKEN", "知识关系目标不存在。"))

    indexed = indexed_object_ids()
    expected = set(notes) | set(snapshots)
    for object_id in expected - indexed:
        issues.append(_issue("warning", "FTS_ENTRY_MISSING", f"FTS 缺少对象：{object_id}"))
    for object_id in indexed - expected:
        issues.append(_issue("warning", "FTS_ENTRY_ORPHAN", f"FTS 存在孤立对象：{object_id}"))

    summary = {
        "errors": sum(item["level"] == "error" for item in issues),
        "warnings": sum(item["level"] == "warning" for item in issues),
        "info": sum(item["level"] == "info" for item in issues),
    }
    return {
        "ok": summary["errors"] == 0,
        "summary": summary,
        "issues": issues,
        "scanned": {"sources": len(snapshot_files), "notes": len(note_files)},
    }
