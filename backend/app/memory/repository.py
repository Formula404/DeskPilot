from __future__ import annotations

from backend.app.db.connection import connect


def search_memory(query: str, limit: int = 5) -> list[dict]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT memory_items.*
            FROM memory_fts
            JOIN memory_items ON memory_items.rowid = memory_fts.rowid
            WHERE memory_fts MATCH ?
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
    return [dict(row) for row in rows]
