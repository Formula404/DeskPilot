from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from backend.app.db.connection import connect
from backend.app.db.repository import get_setting, new_id, now_iso, set_setting

DEFAULT_PROFILE_ID = "profile_default"
ACTIVE_PROFILE_KEY = "knowledge.active_profile_id"
_profile_override: ContextVar[str | None] = ContextVar("knowledge_profile", default=None)


def active_profile_id() -> str:
    override = _profile_override.get()
    if override:
        return override
    return get_setting(ACTIVE_PROFILE_KEY) or DEFAULT_PROFILE_ID


@contextmanager
def use_profile(profile_id: str) -> Iterator[None]:
    token = _profile_override.set(profile_id)
    try:
        yield
    finally:
        _profile_override.reset(token)


def list_profiles() -> list[dict]:
    current = active_profile_id()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT p.*,
              (SELECT COUNT(*) FROM knowledge_profile_sources ps WHERE ps.profile_id = p.id) AS source_count,
              (SELECT COUNT(*) FROM knowledge_profile_notes pn WHERE pn.profile_id = p.id) AS note_count
            FROM knowledge_profiles p ORDER BY is_default DESC, created_at ASC
            """
        ).fetchall()
    return [{**dict(row), "is_active": row["id"] == current} for row in rows]


def get_profile(profile_id: str) -> dict | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM knowledge_profiles WHERE id = ?", (profile_id,)).fetchone()
    return dict(row) if row else None


def create_profile(name: str, description: str = "") -> dict:
    profile_id = f"profile_{new_id().replace('-', '')}"
    now = now_iso()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_profiles(id, name, description, is_default, created_at, updated_at)
            VALUES (?, ?, ?, 0, ?, ?)
            """,
            (profile_id, name.strip(), description.strip(), now, now),
        )
    return next((item for item in list_profiles() if item["id"] == profile_id), {})


def switch_profile(profile_id: str) -> dict:
    profile = get_profile(profile_id)
    if not profile:
        raise ValueError("知识库 Profile 不存在。")
    set_setting(ACTIVE_PROFILE_KEY, profile_id)
    return profile


def delete_profile(profile_id: str) -> None:
    if profile_id == DEFAULT_PROFILE_ID:
        raise ValueError("默认知识库不能删除。")
    if active_profile_id() == profile_id:
        switch_profile(DEFAULT_PROFILE_ID)
    with connect() as connection:
        connection.execute("DELETE FROM knowledge_profiles WHERE id = ?", (profile_id,))


def link_source(source_id: str, profile_id: str | None = None) -> None:
    with connect() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO knowledge_profile_sources(profile_id, source_id) VALUES (?, ?)",
            (profile_id or active_profile_id(), source_id),
        )


def link_note(note_id: str, profile_id: str | None = None) -> None:
    with connect() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO knowledge_profile_notes(profile_id, note_id) VALUES (?, ?)",
            (profile_id or active_profile_id(), note_id),
        )
