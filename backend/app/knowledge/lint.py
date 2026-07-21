from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
import json
import re
from openai import AsyncOpenAI

from backend.app.db.connection import connect
from backend.app.knowledge.indexer import indexed_object_ids
from backend.app.knowledge.markdown import atomic_write, parse_markdown_document, render_note, sha256_text, source_chunks, split_sections
from backend.app.knowledge.models import EvidenceItem, NoteFrontmatter, SourceFrontmatter
from backend.app.knowledge.paths import knowledge_root, profile_workspace
from backend.app.knowledge.source_service import detect_secret
from backend.app.settings.service import get_runtime_settings as get_settings
from backend.app.knowledge.repository import get_note, list_notes, upsert_note
from backend.app.knowledge.indexer import index_note_path, read_indexed_note
from backend.app.knowledge.catalog import append_log
from backend.app.knowledge.settings import get_knowledge_settings
from backend.app.db.repository import new_id, now_iso
from backend.app.knowledge.locking import knowledge_locks


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
        source_status = (sources.get(str(item["source_id"])) or {}).get("status")
        if snapshot_id not in snapshot_files and source_status != "trashed":
            issues.append(_issue("error", "SNAPSHOT_FILE_MISSING", f"快照文件缺失：{snapshot_id}"))
        if item["source_id"] not in sources:
            issues.append(_issue("error", "SNAPSHOT_SOURCE_MISSING", f"快照来源缺失：{snapshot_id}"))
    for snapshot_id, (path, _) in snapshot_files.items():
        if snapshot_id not in snapshots:
            issues.append(_issue("warning", "SNAPSHOT_INDEX_MISSING", "快照未登记到数据库。", path))
    for note_id, item in notes.items():
        if note_id not in note_files and item.get("status") != "trashed":
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
    expected_notes = {note_id for note_id, item in notes.items() if item.get("status") not in {"archived", "trashed"}}
    expected_snapshots = {snapshot_id for snapshot_id, item in snapshots.items() if (sources.get(str(item["source_id"])) or {}).get("status") not in {"archived", "trashed"}}
    expected = expected_notes | expected_snapshots
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


async def semantic_lint_knowledge() -> dict[str, Any]:
    notes = [item for item in list_notes(limit=500) if item.get("status") not in {"archived", "trashed"}]
    pages = []
    inbound: Counter[str] = Counter()
    outbound: Counter[str] = Counter()
    for note in notes:
        note_detail = get_note(str(note["id"])) or note
        frontmatter, sections, _ = read_indexed_note(note_detail)
        for relation in note_detail.get("relations", []):
            inbound[str(relation["to_note_id"])] += 1
            outbound[str(note_detail["id"])] += 1
        pages.append({"id": frontmatter.id, "title": frontmatter.title, "type": frontmatter.entity_type, "status": frontmatter.status, "summary": sections.get("Summary", "")[:500], "tags": frontmatter.tags, "relations": [{"type": item["relation_type"], "target": item["to_note_id"]} for item in note_detail.get("relations", [])]})
    suggestions = []
    isolated = [item for item in pages if not inbound[item["id"]] and not outbound[item["id"]]]
    # One page may be a legitimate graph root. When every page is isolated,
    # choose a stable root and only propose outward links instead of A->B+B->A.
    root_id = min((item["id"] for item in isolated), default=None) if len(isolated) == len(pages) and len(pages) > 1 else None
    for item in isolated:
        if item["id"] == root_id or len(pages) <= 1:
            continue
        candidates = [candidate for candidate in pages if candidate["id"] != item["id"]]
        candidate = max(candidates, key=lambda value: (int(value["id"] == root_id), int(bool(inbound[value["id"]] or outbound[value["id"]])), int(value["type"] == item["type"]), len(set(value["tags"]) & set(item["tags"])), value["title"]))
        suggestions.append({"level": "warning", "code": "ORPHAN_PAGE", "message": f"页面没有入链：{item['title']}", "note_id": item["id"], "note_ids": [item["id"], candidate["id"]], "recommended_action": f"从 {candidate['title']} 添加 related_to 入链", "fix": {"action": "add_relation", "from_note_id": candidate["id"], "to_note_id": item["id"], "relation_type": "related_to", "confidence": 0.5}})
    settings = get_settings()
    model_used = False
    model_pages = pages if get_knowledge_settings().allow_private_remote else [item for item in pages if next((note for note in notes if note["id"] == item["id"]), {}).get("sensitivity") != "private"]
    if settings.openai_api_key and model_pages:
        client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url, timeout=getattr(settings, "request_timeout_seconds", 60))
        try:
            response = await client.chat.completions.create(
                model=settings.openai_model, temperature=getattr(settings, "temperature", 0.2), response_format={"type": "json_object"},
                messages=[{"role": "system", "content": "你是 Wiki 语义维护器。仅基于输入页面，找出矛盾、过时主张、应合并页面、缺失概念、缺失交叉引用和研究空白。输出 JSON {issues:[{level,code,message,note_ids,recommended_action}]}，不要修改文件。"}, {"role": "user", "content": json.dumps({"pages": model_pages}, ensure_ascii=False)}],
            )
            payload = json.loads(response.choices[0].message.content or "{}")
            suggestions.extend(item for item in payload.get("issues", []) if isinstance(item, dict))
            model_used = True
        except Exception:
            __import__("logging").getLogger(__name__).exception("Semantic wiki lint failed")
    run_id = f"lint_{new_id().replace('-', '')}"
    normalized: list[dict[str, Any]] = []
    for index, suggestion in enumerate(suggestions):
        issue = dict(suggestion)
        issue.setdefault("level", "warning")
        issue.setdefault("code", "SEMANTIC_SUGGESTION")
        identity = json.dumps({"run": run_id, "index": index, "code": issue["code"], "note_ids": issue.get("note_ids") or [issue.get("note_id")]}, ensure_ascii=False, sort_keys=True)
        issue["issue_id"] = f"issue_{sha256_text(identity)[:20]}"
        issue["fixable"] = bool(issue.get("fix"))
        normalized.append(issue)
    report = {"run_id": run_id, "issues": normalized, "summary": {"issues": len(normalized), "fixable": sum(bool(item.get("fix")) for item in normalized)}, "scanned": {"notes": len(notes)}, "model_used": model_used, "created_at": now_iso()}
    report_path = profile_workspace() / "lint" / f"{run_id}.json"
    atomic_write(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    append_log("semantic-lint", "Wiki health check", f"Found {len(normalized)} semantic suggestions; model: {model_used}")
    return report


def _sync_relation_note(note_id: str) -> None:
    note = get_note(note_id)
    if not note:
        raise ValueError("关系来源页面不存在。")
    path = knowledge_root() / str(note["markdown_path"])
    content = path.read_text(encoding="utf-8")
    metadata, body = parse_markdown_document(content)
    frontmatter = NoteFrontmatter.model_validate(metadata).model_copy(update={"updated_at": now_iso()})
    _, sections = split_sections(body)
    evidence = [EvidenceItem(source_id=str(item["source_id"]), snapshot_id=str(item["snapshot_id"]), anchor=str(item["evidence_anchor"]), reason="保留的来源证据") for item in note.get("sources", []) if item.get("snapshot_id") and item.get("evidence_anchor")]
    relation_lines = [f"`{item['relation_type']}` `{item['to_note_id']}`" for item in note.get("relations", [])]
    questions = [line.removeprefix("- ").strip() for line in sections.get("Open Questions", "").splitlines() if line.strip() and "暂无" not in line]
    rendered = render_note(frontmatter, summary=sections.get("Summary", ""), overview=sections.get("Overview", ""), details=sections.get("Details", ""), evidence=evidence, relations=relation_lines, open_questions=questions)
    atomic_write(path, rendered)
    upsert_note(note_id=note_id, entity_type=frontmatter.entity_type, title=frontmatter.title, markdown_path=str(note["markdown_path"]), status=frontmatter.status, review_state=frontmatter.review_state, sensitivity=frontmatter.sensitivity, content_sha256=sha256_text(rendered), created_at=frontmatter.created_at, updated_at=frontmatter.updated_at)
    index_note_path(path)


async def apply_semantic_lint_fix(run_id: str, issue_id: str, *, confirmed: bool) -> dict[str, Any]:
    if not confirmed:
        raise ValueError("语义修复必须明确确认。")
    if not re.fullmatch(r"lint_[a-f0-9]+", run_id) or not re.fullmatch(r"issue_[a-f0-9]+", issue_id):
        raise ValueError("语义检查运行或问题 ID 无效。")
    report_path = profile_workspace() / "lint" / f"{run_id}.json"
    if not report_path.exists():
        raise ValueError("语义检查报告不存在。")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    issue = next((item for item in report.get("issues", []) if item.get("issue_id") == issue_id), None)
    if not issue or not issue.get("fix"):
        raise ValueError("该语义问题没有可自动执行的修复。")
    fix = issue["fix"]
    if fix.get("action") != "add_relation":
        raise ValueError("不支持的语义修复动作。")
    from_note_id, to_note_id = str(fix["from_note_id"]), str(fix["to_note_id"])
    if not get_note(from_note_id) or not get_note(to_note_id):
        raise ValueError("语义修复引用的页面已不存在。")
    with knowledge_locks([f"note:{from_note_id}:write", f"note:{to_note_id}:write"]):
        with connect() as connection:
            connection.execute("INSERT OR IGNORE INTO knowledge_relations(id, from_note_id, relation_type, to_note_id, confidence, created_at) VALUES (?, ?, ?, ?, ?, ?)", (f"rel_{new_id().replace('-', '')}", from_note_id, fix.get("relation_type", "related_to"), to_note_id, float(fix.get("confidence", 0.5)), now_iso()))
        _sync_relation_note(from_note_id)
    verification = await semantic_lint_knowledge()
    still_present = any(item.get("code") == issue.get("code") and item.get("note_id") == issue.get("note_id") for item in verification["issues"])
    append_log("semantic-fix", issue_id, f"Action: {fix['action']}; resolved: {not still_present}")
    return {"run_id": run_id, "issue_id": issue_id, "applied": True, "resolved": not still_present, "verification": verification, "fix": fix}
