from __future__ import annotations

import json
from typing import Any

from backend.app.db.connection import connect
from backend.app.db.repository import new_id, now_iso
from backend.app.knowledge.markdown import normalize_title


def get_source(source_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM knowledge_sources WHERE id = ?", (source_id,)).fetchone()
    return dict(row) if row else None


def get_source_by_uri(source_type: str, canonical_uri: str | None) -> dict[str, Any] | None:
    if canonical_uri is None:
        return None
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM knowledge_sources WHERE source_type = ? AND canonical_uri = ?",
            (source_type, canonical_uri),
        ).fetchone()
    return dict(row) if row else None


def create_source(
    *,
    source_type: str,
    canonical_uri: str | None,
    title: str,
    sensitivity: str,
) -> dict[str, Any]:
    source_id = f"src_{new_id().replace('-', '')}"
    now = now_iso()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_sources
            (id, source_type, canonical_uri, title, sensitivity, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'captured', ?, ?)
            """,
            (source_id, source_type, canonical_uri, title, sensitivity, now, now),
        )
    return get_source(source_id) or {}


def update_source(
    source_id: str,
    *,
    title: str | None = None,
    current_snapshot_id: str | None = None,
    status: str | None = None,
) -> None:
    fields = ["updated_at = ?"]
    values: list[Any] = [now_iso()]
    for name, value in [
        ("title", title),
        ("current_snapshot_id", current_snapshot_id),
        ("status", status),
    ]:
        if value is not None:
            fields.append(f"{name} = ?")
            values.append(value)
    values.append(source_id)
    with connect() as connection:
        connection.execute(
            f"UPDATE knowledge_sources SET {', '.join(fields)} WHERE id = ?",
            values,
        )


def get_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM knowledge_snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
    return item


def get_snapshot_by_hash(source_id: str, content_sha256: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT * FROM knowledge_snapshots
            WHERE source_id = ? AND content_sha256 = ?
            """,
            (source_id, content_sha256),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
    return item


def create_snapshot(
    *,
    snapshot_id: str,
    source_id: str,
    content_sha256: str,
    markdown_path: str,
    captured_at: str,
    browser_context_id: str | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_snapshots
            (id, source_id, content_sha256, markdown_path, browser_context_id,
             captured_at, created_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                source_id,
                content_sha256,
                markdown_path,
                browser_context_id,
                captured_at,
                now_iso(),
                json.dumps(metadata, ensure_ascii=False),
            ),
        )
    return get_snapshot(snapshot_id) or {}


def list_source_snapshots(source_id: str) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM knowledge_snapshots WHERE source_id = ? ORDER BY captured_at DESC",
            (source_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_source_notes_stale(source_id: str) -> int:
    with connect() as connection:
        cursor = connection.execute(
            """
            UPDATE knowledge_notes SET status = 'stale', updated_at = ?
            WHERE status = 'active' AND id IN (
              SELECT note_id FROM knowledge_note_sources WHERE source_id = ?
            )
            """,
            (now_iso(), source_id),
        )
    return cursor.rowcount


def get_note(note_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM knowledge_notes WHERE id = ?", (note_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        source_rows = connection.execute(
            """
            SELECT ns.*, s.title AS source_title, s.canonical_uri, s.sensitivity
            FROM knowledge_note_sources ns
            JOIN knowledge_sources s ON s.id = ns.source_id
            WHERE ns.note_id = ?
            """,
            (note_id,),
        ).fetchall()
        relation_rows = connection.execute(
            """
            SELECT r.*, n.title AS target_title
            FROM knowledge_relations r
            JOIN knowledge_notes n ON n.id = r.to_note_id
            WHERE r.from_note_id = ?
            """,
            (note_id,),
        ).fetchall()
    item["sources"] = [dict(value) for value in source_rows]
    item["relations"] = [dict(value) for value in relation_rows]
    return item


def find_note_by_title(title: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM knowledge_notes WHERE normalized_title = ? AND status != 'archived' LIMIT 1",
            (normalize_title(title),),
        ).fetchone()
    return dict(row) if row else None


def list_notes(
    *,
    query: str | None = None,
    entity_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    clauses = ["1 = 1"]
    values: list[Any] = []
    if query:
        clauses.append("(title LIKE ? OR normalized_title LIKE ?)")
        values.extend([f"%{query}%", f"%{normalize_title(query)}%"])
    if entity_type:
        clauses.append("entity_type = ?")
        values.append(entity_type)
    if status:
        clauses.append("status = ?")
        values.append(status)
    values.extend([limit, offset])
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT * FROM knowledge_notes WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC LIMIT ? OFFSET ?
            """,
            values,
        ).fetchall()
    return [dict(row) for row in rows]


def upsert_note(
    *,
    note_id: str,
    entity_type: str,
    title: str,
    markdown_path: str,
    status: str,
    review_state: str,
    sensitivity: str,
    content_sha256: str,
    created_at: str,
    updated_at: str,
) -> None:
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_notes
            (id, entity_type, title, normalized_title, markdown_path, status,
             review_state, sensitivity, content_sha256, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              entity_type = excluded.entity_type,
              title = excluded.title,
              normalized_title = excluded.normalized_title,
              markdown_path = excluded.markdown_path,
              status = excluded.status,
              review_state = excluded.review_state,
              sensitivity = excluded.sensitivity,
              content_sha256 = excluded.content_sha256,
              updated_at = excluded.updated_at
            """,
            (
                note_id,
                entity_type,
                title,
                normalize_title(title),
                markdown_path,
                status,
                review_state,
                sensitivity,
                content_sha256,
                created_at,
                updated_at,
            ),
        )


def link_note_source(
    *,
    note_id: str,
    source_id: str,
    snapshot_id: str,
    evidence_anchor: str,
) -> None:
    with connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO knowledge_note_sources
            (note_id, source_id, snapshot_id, evidence_anchor)
            VALUES (?, ?, ?, ?)
            """,
            (note_id, source_id, snapshot_id, evidence_anchor),
        )


def replace_note_relations(note_id: str, relations: list[dict[str, Any]], source_id: str) -> None:
    with connect() as connection:
        connection.execute("DELETE FROM knowledge_relations WHERE from_note_id = ?", (note_id,))
        for relation in relations:
            target = relation.get("target_note_id")
            if not target or not get_note(target):
                continue
            connection.execute(
                """
                INSERT OR IGNORE INTO knowledge_relations
                (id, from_note_id, relation_type, to_note_id, source_id, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"rel_{new_id().replace('-', '')}",
                    note_id,
                    relation.get("relation_type", "related_to"),
                    target,
                    source_id,
                    relation.get("confidence", 1.0),
                    now_iso(),
                ),
            )


def create_job(job_type: str, target_id: str | None, input_data: dict[str, Any] | None = None) -> str:
    job_id = f"job_{new_id().replace('-', '')}"
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_jobs
            (id, job_type, target_id, status, input_json, created_at)
            VALUES (?, ?, ?, 'queued', ?, ?)
            """,
            (job_id, job_type, target_id, json.dumps(input_data or {}, ensure_ascii=False), now_iso()),
        )
    return job_id


def update_job(
    job_id: str,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    started_at = now_iso() if status == "running" else None
    finished_at = now_iso() if status in {"committed", "proposed", "failed", "rejected"} else None
    with connect() as connection:
        connection.execute(
            """
            UPDATE knowledge_jobs SET status = ?, attempt_count = attempt_count + ?,
              result_json = ?, error_code = ?, error_message = ?,
              started_at = COALESCE(started_at, ?), finished_at = ?
            WHERE id = ?
            """,
            (
                status,
                1 if status == "running" else 0,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                error_code,
                error_message,
                started_at,
                finished_at,
                job_id,
            ),
        )


def create_proposal(
    *,
    job_id: str,
    operation: str,
    target_note_id: str | None,
    proposal_path: str,
) -> str:
    proposal_id = f"prop_{new_id().replace('-', '')}"
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_proposals
            (id, job_id, operation, target_note_id, proposal_path, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (proposal_id, job_id, operation, target_note_id, proposal_path, now_iso()),
        )
    return proposal_id


def get_proposal(proposal_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM knowledge_proposals WHERE id = ?", (proposal_id,)
        ).fetchone()
    return dict(row) if row else None


def list_proposals(status: str = "pending") -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT p.*, n.title AS target_title
            FROM knowledge_proposals p
            LEFT JOIN knowledge_notes n ON n.id = p.target_note_id
            WHERE p.status = ? ORDER BY p.created_at DESC
            """,
            (status,),
        ).fetchall()
    return [dict(row) for row in rows]


def resolve_proposal(proposal_id: str, status: str) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE knowledge_proposals SET status = ?, resolved_at = ? WHERE id = ?",
            (status, now_iso(), proposal_id),
        )


def source_has_pending_proposals(source_id: str) -> bool:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM knowledge_proposals p
            JOIN knowledge_jobs j ON j.id = p.job_id
            WHERE j.target_id = ? AND p.status = 'pending'
            LIMIT 1
            """,
            (source_id,),
        ).fetchone()
    return row is not None


def knowledge_counts() -> dict[str, int]:
    queries = {
        "sources": "SELECT COUNT(*) FROM knowledge_sources WHERE status != 'archived'",
        "snapshots": "SELECT COUNT(*) FROM knowledge_snapshots",
        "notes": "SELECT COUNT(*) FROM knowledge_notes WHERE status != 'archived'",
        "stale_notes": "SELECT COUNT(*) FROM knowledge_notes WHERE status = 'stale'",
        "pending_proposals": "SELECT COUNT(*) FROM knowledge_proposals WHERE status = 'pending'",
    }
    with connect() as connection:
        return {name: int(connection.execute(sql).fetchone()[0]) for name, sql in queries.items()}
