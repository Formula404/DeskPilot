from __future__ import annotations

from datetime import UTC, datetime
import re

from backend.app.context.security import contains_secret
from backend.app.db.connection import connect
from backend.app.db.repository import new_id, now_iso


def search_memory(query: str, limit: int = 5) -> list[dict]:
    latin_terms = re.findall(r"[A-Za-z0-9_]{2,}", query)
    chinese_runs = re.findall(r"[\u4e00-\u9fff]{2,}", query)
    chinese_terms = [
        run[index : index + 2]
        for run in chinese_runs
        for index in range(max(1, len(run) - 1))
    ]
    terms = [*latin_terms, *chinese_terms][:20]
    if not terms:
        return []
    fts_query = " OR ".join(f'"{term}"' for term in terms)
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT memory_items.*
            FROM memory_fts
            JOIN memory_items ON memory_items.rowid = memory_fts.rowid
            WHERE memory_fts MATCH ?
              AND memory_items.status = 'active'
              AND memory_items.sensitivity != 'secret'
              AND (memory_items.expires_at IS NULL OR memory_items.expires_at > ?)
            ORDER BY bm25(memory_fts), memory_items.confidence DESC, memory_items.updated_at DESC
            LIMIT ?
            """,
            (fts_query, datetime.now(UTC).isoformat(), limit),
        ).fetchall()
    return [dict(row) for row in rows]


def save_memory(
    *,
    kind: str,
    content: str,
    source_task_id: str | None = None,
    sensitivity: str = "normal",
    source_type: str = "user_explicit",
    confidence: float = 1.0,
    expires_at: str | None = None,
) -> str:
    if kind not in {"preference", "fact", "procedure", "episodic_summary"}:
        raise ValueError("Unsupported memory kind")
    if sensitivity == "secret" or contains_secret(content):
        raise ValueError("Secret content cannot be written to long-term memory")
    memory_id = new_id()
    now = now_iso()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO memory_items
            (id, kind, content, source_task_id, sensitivity, confidence, source_type,
             expires_at, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (
                memory_id,
                kind,
                content,
                source_task_id,
                sensitivity,
                confidence,
                source_type,
                expires_at,
                now,
                now,
            ),
        )
    return memory_id


def list_memories(limit: int = 100) -> list[dict]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, kind, content, source_task_id, sensitivity, confidence,
                   source_type, expires_at, status, created_at, updated_at
            FROM memory_items ORDER BY updated_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_memory(memory_id: str) -> bool:
    with connect() as connection:
        cursor = connection.execute("DELETE FROM memory_items WHERE id = ?", (memory_id,))
    return cursor.rowcount > 0
