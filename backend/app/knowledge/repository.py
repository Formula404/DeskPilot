from __future__ import annotations

import json
import sqlite3
from typing import Any

from backend.app.db.connection import connect
from backend.app.db.repository import new_id, now_iso
from backend.app.knowledge.markdown import normalize_title
from backend.app.knowledge.profiles import active_profile_id, link_note, link_source


def get_source(source_id: str, *, include_trashed: bool = False) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT s.* FROM knowledge_sources s JOIN knowledge_profile_sources ps ON ps.source_id=s.id "
            "WHERE s.id=? AND ps.profile_id=?" + ("" if include_trashed else " AND s.status!='trashed'"),
            (source_id, active_profile_id()),
        ).fetchone()
    return dict(row) if row else None


def get_source_by_uri(source_type: str, canonical_uri: str | None) -> dict[str, Any] | None:
    if canonical_uri is None:
        return None
    with connect() as connection:
        row = connection.execute(
            "SELECT s.* FROM knowledge_sources s JOIN knowledge_profile_sources ps ON ps.source_id=s.id WHERE s.source_type=? AND s.canonical_uri=? AND ps.profile_id=?",
            (source_type, canonical_uri, active_profile_id()),
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
    try:
      with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_sources
            (id, source_type, canonical_uri, title, sensitivity, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'captured', ?, ?)
            """,
            (source_id, source_type, canonical_uri, title, sensitivity, now, now),
        )
    except sqlite3.IntegrityError:
      with connect() as connection:
        row = connection.execute("SELECT id FROM knowledge_sources WHERE source_type=? AND canonical_uri=?", (source_type, canonical_uri)).fetchone()
      if not row:
        raise
      source_id = str(row["id"])
    link_source(source_id)
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
            "SELECT sn.* FROM knowledge_snapshots sn JOIN knowledge_profile_sources ps ON ps.source_id=sn.source_id WHERE sn.id=? AND ps.profile_id=?", (snapshot_id, active_profile_id())
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


def list_sources(
    *,
    query: str | None = None,
    source_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    clauses = ["1 = 1" if status else "s.status != 'trashed'"]
    values: list[Any] = []
    if query:
        clauses.append("(title LIKE ? OR canonical_uri LIKE ?)")
        values.extend([f"%{query}%", f"%{query}%"])
    if source_type:
        clauses.append("source_type = ?")
        values.append(source_type)
    if status:
        clauses.append("status = ?")
        values.append(status)
    values.extend([limit, offset])
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT s.*,
                   (SELECT COUNT(*) FROM knowledge_snapshots sn WHERE sn.source_id = s.id) AS snapshot_count,
                   (SELECT COUNT(DISTINCT note_id) FROM knowledge_note_sources ns WHERE ns.source_id = s.id) AS note_count
            FROM knowledge_sources s
            JOIN knowledge_profile_sources ps ON ps.source_id = s.id
            WHERE {' AND '.join(clauses)} AND ps.profile_id = ?
            ORDER BY s.updated_at DESC LIMIT ? OFFSET ?
            """,
            [*values[:-2], active_profile_id(), *values[-2:]],
        ).fetchall()
    return [dict(row) for row in rows]


def count_sources(
    *,
    query: str | None = None,
    source_type: str | None = None,
    status: str | None = None,
) -> int:
    clauses = ["1 = 1" if status else "s.status != 'trashed'"]
    values: list[Any] = []
    if query:
        clauses.append("(title LIKE ? OR canonical_uri LIKE ?)")
        values.extend([f"%{query}%", f"%{query}%"])
    if source_type:
        clauses.append("source_type = ?")
        values.append(source_type)
    if status:
        clauses.append("status = ?")
        values.append(status)
    with connect() as connection:
        row = connection.execute(
            f"SELECT COUNT(*) FROM knowledge_sources s JOIN knowledge_profile_sources ps ON ps.source_id=s.id WHERE {' AND '.join(clauses)} AND ps.profile_id=?",
            [*values, active_profile_id()],
        ).fetchone()
    return int(row[0])


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


def get_note(note_id: str, *, include_trashed: bool = False) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT n.* FROM knowledge_notes n JOIN knowledge_profile_notes pn ON pn.note_id=n.id "
            "WHERE n.id=? AND pn.profile_id=?" + ("" if include_trashed else " AND n.status!='trashed'"),
            (note_id, active_profile_id()),
        ).fetchone()
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


def list_notes_by_source(source_id: str) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT n.* FROM knowledge_notes n
            JOIN knowledge_note_sources ns ON ns.note_id = n.id
            JOIN knowledge_profile_notes pn ON pn.note_id = n.id
            WHERE ns.source_id = ? AND pn.profile_id = ? AND n.status != 'archived'
            ORDER BY n.updated_at DESC
            """,
            (source_id, active_profile_id()),
        ).fetchall()
    return [dict(row) for row in rows]


def find_note_by_title(title: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT n.* FROM knowledge_notes n JOIN knowledge_profile_notes pn ON pn.note_id=n.id WHERE n.normalized_title=? AND n.status!='archived' AND pn.profile_id=? LIMIT 1",
            (normalize_title(title), active_profile_id()),
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
    clauses = ["1 = 1" if status else "n.status != 'trashed'"]
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
            SELECT n.* FROM knowledge_notes n
            JOIN knowledge_profile_notes pn ON pn.note_id=n.id
            WHERE {' AND '.join(clauses)} AND pn.profile_id=?
            ORDER BY updated_at DESC LIMIT ? OFFSET ?
            """,
            [*values[:-2], active_profile_id(), *values[-2:]],
        ).fetchall()
    return [dict(row) for row in rows]


def count_notes(
    *,
    query: str | None = None,
    entity_type: str | None = None,
    status: str | None = None,
) -> int:
    clauses = ["1 = 1" if status else "n.status != 'trashed'"]
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
    with connect() as connection:
        row = connection.execute(
            f"SELECT COUNT(*) FROM knowledge_notes n JOIN knowledge_profile_notes pn ON pn.note_id=n.id WHERE {' AND '.join(clauses)} AND pn.profile_id=?",
            [*values, active_profile_id()],
        ).fetchone()
    return int(row[0])


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

    link_note(note_id)


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


def expand_note_relations(
    seed_note_ids: list[str], *, depth: int = 2, max_nodes: int = 20
) -> list[dict[str, Any]]:
    """Breadth-first relation expansion over both inbound and outbound profile-visible edges."""
    seeds = list(dict.fromkeys(seed_note_ids))
    if not seeds or depth < 1 or max_nodes < 1:
        return []
    visited = set(seeds)
    frontier: list[tuple[str, list[dict[str, Any]]]] = [(seed, []) for seed in seeds]
    expanded: list[dict[str, Any]] = []
    profile_id = active_profile_id()
    for hop in range(1, min(depth, 3) + 1):
        next_frontier: list[tuple[str, list[dict[str, Any]]]] = []
        for current_id, path in frontier:
            with connect() as connection:
                rows = connection.execute(
                    """
                    SELECT r.*, CASE WHEN r.from_note_id=? THEN r.to_note_id ELSE r.from_note_id END AS neighbor_id,
                      CASE WHEN r.from_note_id=? THEN 'outbound' ELSE 'inbound' END AS direction,
                      n.title AS neighbor_title, n.entity_type, n.status, n.markdown_path
                    FROM knowledge_relations r
                    JOIN knowledge_notes n ON n.id=CASE WHEN r.from_note_id=? THEN r.to_note_id ELSE r.from_note_id END
                    JOIN knowledge_profile_notes pn ON pn.note_id=n.id AND pn.profile_id=?
                    WHERE (r.from_note_id=? OR r.to_note_id=?) AND n.status NOT IN ('archived','trashed')
                    ORDER BY COALESCE(r.confidence, 1.0) DESC, r.created_at ASC
                    """,
                    (current_id, current_id, current_id, profile_id, current_id, current_id),
                ).fetchall()
            for row in rows:
                neighbor_id = str(row["neighbor_id"])
                if neighbor_id in visited:
                    continue
                edge = {
                    "from_note_id": str(row["from_note_id"]),
                    "to_note_id": str(row["to_note_id"]),
                    "relation_type": str(row["relation_type"]),
                    "direction": str(row["direction"]),
                    "confidence": float(row["confidence"] or 1.0),
                    "source_id": row["source_id"],
                }
                relation_path = [*path, edge]
                score = 1.0
                for index, item in enumerate(relation_path, start=1):
                    score *= float(item["confidence"]) * (0.7 if index > 1 else 0.85)
                expanded.append({"note_id": neighbor_id, "title": row["neighbor_title"], "entity_type": row["entity_type"], "status": row["status"], "markdown_path": row["markdown_path"], "hop": hop, "relation_score": score, "relation_path": relation_path})
                visited.add(neighbor_id)
                next_frontier.append((neighbor_id, relation_path))
                if len(expanded) >= max_nodes:
                    return expanded
        frontier = next_frontier
        if not frontier:
            break
    return expanded


def create_job(
    job_type: str,
    target_id: str | None,
    input_data: dict[str, Any] | None = None,
    *,
    profile_id: str | None = None,
    max_attempts: int = 3,
) -> str:
    job_id = f"job_{new_id().replace('-', '')}"
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_jobs
            (id, job_type, target_id, status, input_json, profile_id, max_attempts, created_at, updated_at)
            VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?)
            """,
            (job_id, job_type, target_id, json.dumps(input_data or {}, ensure_ascii=False), profile_id or active_profile_id(), max_attempts, now_iso(), now_iso()),
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
    finished_at = now_iso() if status in {"committed", "proposed", "failed", "rejected", "completed", "cancelled"} else None
    with connect() as connection:
        connection.execute(
            """
            UPDATE knowledge_jobs SET status = ?, attempt_count = attempt_count + ?, updated_at=?,
              result_json = ?, error_code = ?, error_message = ?,
              started_at = COALESCE(started_at, ?), finished_at = ?
            WHERE id = ?
            """,
            (
                status,
                1 if status == "running" else 0,
                now_iso(),
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                error_code,
                error_message,
                started_at,
                finished_at,
                job_id,
            ),
        )


def get_job(job_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM knowledge_jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["input"] = json.loads(item.get("input_json") or "{}")
    item["result"] = json.loads(item.get("result_json") or "null")
    return item


def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM knowledge_jobs WHERE profile_id=? ORDER BY created_at DESC LIMIT ?",
            (active_profile_id(), limit),
        ).fetchall()
    return [dict(row) for row in rows]


def update_job_progress(job_id: str, progress: int) -> None:
    with connect() as connection:
        connection.execute(
            "UPDATE knowledge_jobs SET progress=?, updated_at=? WHERE id=?",
            (max(0, min(100, progress)), now_iso(), job_id),
        )


def request_job_cancel(job_id: str) -> bool:
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE knowledge_jobs SET cancel_requested=1, updated_at=? "
            "WHERE id=? AND status IN ('queued','running')",
            (now_iso(), job_id),
        )
    return cursor.rowcount > 0


def reset_job_for_retry(job_id: str) -> bool:
    with connect() as connection:
        cursor = connection.execute(
            """
            UPDATE knowledge_jobs SET status='queued', progress=0, cancel_requested=0,
              result_json=NULL, error_code=NULL, error_message=NULL, started_at=NULL,
              finished_at=NULL, updated_at=?
            WHERE id=? AND status IN ('failed','cancelled') AND attempt_count < max_attempts
            """,
            (now_iso(), job_id),
        )
    return cursor.rowcount > 0


def add_job_event(job_id: str, event_type: str, progress: int, message: str, payload: dict | None = None) -> dict[str, Any]:
    event_id = f"kje_{new_id().replace('-', '')}"
    created = now_iso()
    with connect() as connection:
        connection.execute(
            "INSERT INTO knowledge_job_events(id, job_id, event_type, progress, message, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event_id, job_id, event_type, progress, message, json.dumps(payload or {}, ensure_ascii=False), created),
        )
    return {"id": event_id, "job_id": job_id, "event_type": event_type, "progress": progress, "message": message, "payload": payload or {}, "created_at": created}


def list_job_events(job_id: str) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute("SELECT * FROM knowledge_job_events WHERE job_id=? ORDER BY created_at", (job_id,)).fetchall()
    return [{**dict(row), "payload": json.loads(row["payload_json"] or "{}")} for row in rows]


def create_proposal(
    *,
    job_id: str,
    operation: str,
    target_note_id: str | None,
    proposal_path: str,
    base_note_sha256: str | None = None,
    base_snapshot_id: str | None = None,
) -> str:
    proposal_id = f"prop_{new_id().replace('-', '')}"
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_proposals
            (id, job_id, operation, target_note_id, proposal_path, base_note_sha256,
             base_snapshot_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (proposal_id, job_id, operation, target_note_id, proposal_path,
             base_note_sha256, base_snapshot_id, now_iso()),
        )
    return proposal_id


def get_proposal(proposal_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT p.* FROM knowledge_proposals p
            JOIN knowledge_jobs j ON j.id = p.job_id
            WHERE p.id = ? AND (
              j.target_id IN (SELECT source_id FROM knowledge_profile_sources WHERE profile_id = ?)
              OR p.target_note_id IN (SELECT note_id FROM knowledge_profile_notes WHERE profile_id = ?)
            )
            """,
            (proposal_id, active_profile_id(), active_profile_id()),
        ).fetchone()
    return dict(row) if row else None


def list_proposals(status: str = "pending") -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT p.*, n.title AS target_title
            FROM knowledge_proposals p
            JOIN knowledge_jobs j ON j.id = p.job_id
            LEFT JOIN knowledge_notes n ON n.id = p.target_note_id
            WHERE p.status = ? AND (
              j.target_id IN (SELECT source_id FROM knowledge_profile_sources WHERE profile_id = ?)
              OR p.target_note_id IN (SELECT note_id FROM knowledge_profile_notes WHERE profile_id = ?)
            ) ORDER BY p.created_at DESC
            """,
            (status, active_profile_id(), active_profile_id()),
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


def recover_interrupted_jobs() -> dict[str, Any]:
    """Make jobs left running by a dead process replayable without duplicating proposals."""
    with connect() as connection:
        proposed = connection.execute(
            """
            UPDATE knowledge_jobs SET status='proposed', finished_at=?,
              error_code='KNOWLEDGE_PROCESS_INTERRUPTED',
              error_message='Recovered after process interruption; pending proposal retained.'
            WHERE status='running' AND EXISTS (
              SELECT 1 FROM knowledge_proposals p
              WHERE p.job_id=knowledge_jobs.id AND p.status='pending'
            )
            """,
            (now_iso(),),
        ).rowcount
        queued = connection.execute(
            """
            UPDATE knowledge_jobs SET status='queued', started_at=NULL, finished_at=NULL,
              error_code='KNOWLEDGE_PROCESS_INTERRUPTED',
              error_message='Recovered after process interruption and queued for retry.'
            WHERE status='running'
            """
        ).rowcount
        rows = connection.execute(
            "SELECT id, target_id, job_type, input_json, profile_id FROM knowledge_jobs "
            "WHERE status='queued' ORDER BY created_at"
        ).fetchall()
    return {
        "queued": queued,
        "proposed": proposed,
        "jobs": [dict(row) for row in rows],
    }


def knowledge_counts() -> dict[str, int]:
    profile_id = active_profile_id()
    with connect() as connection:
        sources = int(connection.execute("SELECT COUNT(*) FROM knowledge_profile_sources WHERE profile_id=?", (profile_id,)).fetchone()[0])
        snapshots = int(connection.execute("SELECT COUNT(*) FROM knowledge_snapshots WHERE source_id IN (SELECT source_id FROM knowledge_profile_sources WHERE profile_id=?)", (profile_id,)).fetchone()[0])
        notes = int(connection.execute("SELECT COUNT(*) FROM knowledge_profile_notes WHERE profile_id=?", (profile_id,)).fetchone()[0])
        stale = int(connection.execute("SELECT COUNT(*) FROM knowledge_notes WHERE status='stale' AND id IN (SELECT note_id FROM knowledge_profile_notes WHERE profile_id=?)", (profile_id,)).fetchone()[0])
    return {"sources": sources, "snapshots": snapshots, "notes": notes, "stale_notes": stale, "pending_proposals": len(list_proposals())}
