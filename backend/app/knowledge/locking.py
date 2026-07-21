from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import time

from backend.app.db.connection import connect
from backend.app.db.repository import new_id, now_iso


class KnowledgeLockBusy(RuntimeError):
    code = "KNOWLEDGE_RESOURCE_BUSY"


def _expires_at(lease_seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).isoformat()


def acquire_lock(resource_key: str, *, owner_id: str, lease_seconds: int = 900) -> None:
    """Atomically acquire a cross-process SQLite lease for a knowledge resource."""
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM knowledge_locks WHERE expires_at <= ?", (now_iso(),))
        try:
            connection.execute(
                "INSERT INTO knowledge_locks(resource_key, owner_id, acquired_at, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (resource_key, owner_id, now_iso(), _expires_at(lease_seconds)),
            )
        except Exception as exc:
            if "UNIQUE constraint failed" not in str(exc):
                raise
            raise KnowledgeLockBusy(f"知识资源正在被另一个任务处理：{resource_key}") from exc


def release_lock(resource_key: str, *, owner_id: str) -> None:
    with connect() as connection:
        connection.execute(
            "DELETE FROM knowledge_locks WHERE resource_key = ? AND owner_id = ?",
            (resource_key, owner_id),
        )


@contextmanager
def knowledge_locks(
    resource_keys: Sequence[str], *, owner_id: str | None = None, lease_seconds: int = 900, wait_seconds: float = 0
) -> Iterator[str]:
    owner = owner_id or f"lock_{new_id().replace('-', '')}"
    acquired: list[str] = []
    try:
        for key in sorted(set(resource_keys)):
            deadline = time.monotonic() + wait_seconds
            while True:
                try:
                    acquire_lock(key, owner_id=owner, lease_seconds=lease_seconds)
                    break
                except KnowledgeLockBusy:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.02)
            acquired.append(key)
        yield owner
    finally:
        for key in reversed(acquired):
            release_lock(key, owner_id=owner)
