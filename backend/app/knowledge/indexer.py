from __future__ import annotations

import re
import logging
from pathlib import Path
from typing import Any

from backend.app.db.connection import connect
from backend.app.knowledge.markdown import parse_markdown_document, split_sections
from backend.app.knowledge.chinese_search import indexed_text, search_terms
from backend.app.knowledge.models import NoteFrontmatter, SourceFrontmatter
from backend.app.knowledge.paths import from_knowledge_relative, knowledge_root
from backend.app.knowledge.paths import relative_to_knowledge
from backend.app.knowledge.repository import link_note_source, upsert_note
from backend.app.knowledge.profiles import DEFAULT_PROFILE_ID, active_profile_id, link_source, use_profile

logger = logging.getLogger(__name__)


def index_note_path(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    metadata, body = parse_markdown_document(content)
    frontmatter = NoteFrontmatter.model_validate(metadata)
    _, sections = split_sections(body)
    with connect() as connection:
        connection.execute("DELETE FROM knowledge_fts WHERE object_id = ?", (frontmatter.id,))
        connection.execute(
            """
            INSERT INTO knowledge_fts
            (object_id, object_kind, title, aliases, summary, body, tags)
            VALUES (?, 'note', ?, ?, ?, ?, ?)
            """,
            (
                frontmatter.id,
                frontmatter.title,
                " ".join(frontmatter.aliases),
                sections.get("Summary", ""),
                indexed_text(body),
                " ".join(frontmatter.tags),
            ),
        )
    return {"id": frontmatter.id, "title": frontmatter.title, "kind": "note"}


def index_source_path(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    metadata, body = parse_markdown_document(content)
    frontmatter = SourceFrontmatter.model_validate(metadata)
    with connect() as connection:
        connection.execute("DELETE FROM knowledge_fts WHERE object_id = ?", (frontmatter.snapshot_id,))
        connection.execute(
            """
            INSERT INTO knowledge_fts
            (object_id, object_kind, title, aliases, summary, body, tags)
            VALUES (?, 'source', ?, '', '', ?, '')
            """,
            (frontmatter.snapshot_id, frontmatter.title, indexed_text(body)),
        )
    return {"id": frontmatter.snapshot_id, "title": frontmatter.title, "kind": "source"}


def _fts_expression(query: str) -> str:
    terms = search_terms(query, 12) or [term for term in re.findall(r"[\w\u4e00-\u9fff]+", query) if term]
    return " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms[:12])


def search_index(query: str, limit: int = 8) -> list[dict[str, Any]]:
    expression = _fts_expression(query)
    rows: list[Any] = []
    if expression:
        try:
            with connect() as connection:
                rows = connection.execute(
                    """
                    SELECT object_id, object_kind, title, summary,
                           bm25(knowledge_fts, 0, 0, 8, 3, 1, 2) AS rank
                    FROM knowledge_fts
                    WHERE knowledge_fts MATCH ? AND (
                      (object_kind = 'note' AND object_id IN (
                        SELECT note_id FROM knowledge_profile_notes WHERE profile_id = ?
                      )) OR (object_kind = 'source' AND object_id IN (
                        SELECT current_snapshot_id FROM knowledge_sources
                        WHERE id IN (SELECT source_id FROM knowledge_profile_sources WHERE profile_id = ?)
                      ))
                    )
                    ORDER BY rank LIMIT ?
                    """,
                    (expression, active_profile_id(), active_profile_id(), limit),
                ).fetchall()
        except Exception:
            logger.exception("Knowledge FTS MATCH query failed; using LIKE fallback")
            rows = []

    results = [dict(row) for row in rows]
    seen = {str(item["object_id"]) for item in results}
    fallback_terms = search_terms(query, 8) or [query]
    text_clauses = " OR ".join("(title LIKE ? OR aliases LIKE ? OR body LIKE ?)" for _ in fallback_terms)
    text_values = [value for term in fallback_terms for value in (f"%{term}%", f"%{term}%", f"%{term}%")]
    with connect() as connection:
        fallback = connection.execute(
            f"""
            SELECT object_id, object_kind, title, summary, 1000.0 AS rank
            FROM knowledge_fts
            WHERE ({text_clauses}) AND (
              (object_kind = 'note' AND object_id IN (
                SELECT note_id FROM knowledge_profile_notes WHERE profile_id = ?
              )) OR (object_kind = 'source' AND object_id IN (
                SELECT current_snapshot_id FROM knowledge_sources
                WHERE id IN (SELECT source_id FROM knowledge_profile_sources WHERE profile_id = ?)
              ))
            )
            LIMIT ?
            """,
            (*text_values, active_profile_id(), active_profile_id(), limit),
        ).fetchall()
    for row in fallback:
        item = dict(row)
        if str(item["object_id"]) not in seen:
            results.append(item)
            seen.add(str(item["object_id"]))
    return results[:limit]


def rebuild_index() -> dict[str, int]:
    with connect() as connection:
        connection.execute("DELETE FROM knowledge_fts")
    counts = {"notes": 0, "sources": 0, "errors": 0}
    root = knowledge_root()
    for path in (root / "sources").rglob("*.md"):
        try:
            metadata, _ = parse_markdown_document(path.read_text(encoding="utf-8"))
            frontmatter = SourceFrontmatter.model_validate(metadata)
            relative = relative_to_knowledge(path)
            with connect() as connection:
                connection.execute(
                    """
                    INSERT INTO knowledge_sources
                    (id, source_type, canonical_uri, title, current_snapshot_id,
                     sensitivity, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                      title = excluded.title,
                      canonical_uri = excluded.canonical_uri,
                      sensitivity = excluded.sensitivity,
                      updated_at = excluded.updated_at
                    """,
                    (
                        frontmatter.id,
                        frontmatter.source_type,
                        frontmatter.canonical_uri,
                        frontmatter.title,
                        frontmatter.snapshot_id,
                        frontmatter.sensitivity,
                        frontmatter.captured_at,
                        frontmatter.captured_at,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO knowledge_snapshots
                    (id, source_id, content_sha256, markdown_path, browser_context_id,
                     captured_at, created_at, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, '{}')
                    ON CONFLICT(id) DO UPDATE SET
                      markdown_path = excluded.markdown_path,
                      content_sha256 = excluded.content_sha256
                    """,
                    (
                        frontmatter.snapshot_id,
                        frontmatter.id,
                        frontmatter.content_sha256,
                        relative,
                        frontmatter.browser_context_id,
                        frontmatter.captured_at,
                        frontmatter.captured_at,
                    ),
                )
                current = connection.execute(
                    """
                    SELECT s.captured_at FROM knowledge_sources k
                    LEFT JOIN knowledge_snapshots s ON s.id = k.current_snapshot_id
                    WHERE k.id = ?
                    """,
                    (frontmatter.id,),
                ).fetchone()
                if not current or not current[0] or frontmatter.captured_at >= str(current[0]):
                    connection.execute(
                        "UPDATE knowledge_sources SET current_snapshot_id = ? WHERE id = ?",
                        (frontmatter.snapshot_id, frontmatter.id),
                    )
            index_source_path(path)
            link_source(frontmatter.id, DEFAULT_PROFILE_ID)
            counts["sources"] += 1
        except Exception:
            counts["errors"] += 1

    note_documents: list[tuple[Path, NoteFrontmatter, dict[str, str], str]] = []
    with use_profile(DEFAULT_PROFILE_ID):
      for path in (root / "notes").rglob("*.md"):
        try:
            metadata, body = parse_markdown_document(path.read_text(encoding="utf-8"))
            frontmatter = NoteFrontmatter.model_validate(metadata)
            _, sections = split_sections(body)
            rendered = path.read_text(encoding="utf-8")
            upsert_note(
                note_id=frontmatter.id,
                entity_type=frontmatter.entity_type,
                title=frontmatter.title,
                markdown_path=relative_to_knowledge(path),
                status=frontmatter.status,
                review_state=frontmatter.review_state,
                sensitivity=frontmatter.sensitivity,
                content_sha256=__import__("hashlib").sha256(rendered.encode("utf-8")).hexdigest(),
                created_at=frontmatter.created_at,
                updated_at=frontmatter.updated_at,
            )
            index_note_path(path)
            note_documents.append((path, frontmatter, sections, rendered))
            counts["notes"] += 1
        except Exception:
            counts["errors"] += 1

    evidence_pattern = re.compile(
        r"^- `(?P<source>src_[^`]+)` / `(?P<snapshot>snap_[^#`]+)#(?P<anchor>chunk-\d+)`:",
        re.MULTILINE,
    )
    relation_pattern = re.compile(
        r"^- `(?P<type>related_to|depends_on|used_by|part_of|contradicts|supports)` `(?P<target>note_[^`]+)`",
        re.MULTILINE,
    )
    for _, frontmatter, sections, _ in note_documents:
        try:
            for match in evidence_pattern.finditer(sections.get("Evidence", "")):
                link_note_source(
                    note_id=frontmatter.id,
                    source_id=match.group("source"),
                    snapshot_id=match.group("snapshot"),
                    evidence_anchor=match.group("anchor"),
                )
            with connect() as connection:
                for match in relation_pattern.finditer(sections.get("Relations", "")):
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO knowledge_relations
                        (id, from_note_id, relation_type, to_note_id, confidence, created_at)
                        VALUES (lower(hex(randomblob(16))), ?, ?, ?, 1.0, datetime('now'))
                        """,
                        (frontmatter.id, match.group("type"), match.group("target")),
                    )
        except Exception:
            counts["errors"] += 1
    return counts


def remove_from_index(object_id: str) -> None:
    with connect() as connection:
        connection.execute("DELETE FROM knowledge_fts WHERE object_id = ?", (object_id,))


def indexed_object_ids() -> set[str]:
    with connect() as connection:
        rows = connection.execute("SELECT object_id FROM knowledge_fts").fetchall()
    return {str(row[0]) for row in rows}


def read_indexed_note(note: dict[str, Any]) -> tuple[NoteFrontmatter, dict[str, str], str]:
    path = from_knowledge_relative(str(note["markdown_path"]))
    content = path.read_text(encoding="utf-8")
    metadata, body = parse_markdown_document(content)
    frontmatter = NoteFrontmatter.model_validate(metadata)
    _, sections = split_sections(body)
    return frontmatter, sections, content
