from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

import shutil
import yaml

from backend.app.db.connection import connect
from backend.app.db.repository import get_setting, new_id, now_iso, set_setting

DEFAULT_PROFILE_ID = "profile_default"
ACTIVE_PROFILE_KEY = "knowledge.active_profile_id"
_profile_override: ContextVar[str | None] = ContextVar("knowledge_profile", default=None)


def _manifest_path(profile_id: str):
    from backend.app.knowledge.paths import profile_workspace

    return profile_workspace(profile_id) / "profile.yaml"


def sync_profile_manifest(profile_id: str) -> None:
    from backend.app.knowledge.markdown import atomic_write

    with connect() as connection:
        profile = connection.execute("SELECT * FROM knowledge_profiles WHERE id=?", (profile_id,)).fetchone()
        if not profile:
            return
        source_ids = [str(row[0]) for row in connection.execute("SELECT source_id FROM knowledge_profile_sources WHERE profile_id=? ORDER BY source_id", (profile_id,)).fetchall()]
        note_ids = [str(row[0]) for row in connection.execute("SELECT note_id FROM knowledge_profile_notes WHERE profile_id=? ORDER BY note_id", (profile_id,)).fetchall()]
    payload = {
        "schema_version": 1,
        "id": profile["id"],
        "name": profile["name"],
        "description": profile["description"],
        "is_default": bool(profile["is_default"]),
        "created_at": profile["created_at"],
        "updated_at": profile["updated_at"],
        "source_ids": source_ids,
        "note_ids": note_ids,
    }
    atomic_write(_manifest_path(profile_id), yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))


def load_profile_manifests() -> list[dict]:
    from backend.app.knowledge.paths import knowledge_root

    manifests: list[dict] = []
    for path in (knowledge_root() / "profiles").glob("*/profile.yaml"):
        try:
            item = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(item, dict) and item.get("id") == path.parent.name:
                manifests.append(item)
        except (OSError, yaml.YAMLError):
            continue
    return manifests


def rebuild_profiles_from_files(manifests: list[dict] | None = None) -> dict[str, int | str]:
    from backend.app.knowledge.paths import knowledge_root

    items = manifests if manifests is not None else load_profile_manifests()
    if not items:
        sync_profile_manifest(DEFAULT_PROFILE_ID)
        items = load_profile_manifests()
    with connect() as connection:
        for item in items:
            connection.execute(
                """
                INSERT INTO knowledge_profiles(id, name, description, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, description=excluded.description,
                  is_default=excluded.is_default, created_at=excluded.created_at, updated_at=excluded.updated_at
                """,
                (item["id"], item.get("name") or "知识库", item.get("description") or "", int(bool(item.get("is_default"))), item.get("created_at") or now_iso(), item.get("updated_at") or now_iso()),
            )
        connection.execute("DELETE FROM knowledge_profile_sources")
        connection.execute("DELETE FROM knowledge_profile_notes")
        for item in items:
            for source_id in item.get("source_ids", []):
                connection.execute("INSERT OR IGNORE INTO knowledge_profile_sources(profile_id, source_id) SELECT ?, id FROM knowledge_sources WHERE id=?", (item["id"], source_id))
            for note_id in item.get("note_ids", []):
                connection.execute("INSERT OR IGNORE INTO knowledge_profile_notes(profile_id, note_id) SELECT ?, id FROM knowledge_notes WHERE id=?", (item["id"], note_id))
    active_file = knowledge_root() / "profiles" / "active-profile.txt"
    requested = active_file.read_text(encoding="utf-8").strip() if active_file.exists() else DEFAULT_PROFILE_ID
    known = {str(item["id"]) for item in items}
    active = requested if requested in known else DEFAULT_PROFILE_ID
    set_setting(ACTIVE_PROFILE_KEY, active)
    for item in items:
        sync_profile_manifest(str(item["id"]))
    return {"profiles": len(items), "active_profile_id": active}


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
    sync_profile_manifest(profile_id)
    return next((item for item in list_profiles() if item["id"] == profile_id), {})


def switch_profile(profile_id: str) -> dict:
    profile = get_profile(profile_id)
    if not profile:
        raise ValueError("知识库 Profile 不存在。")
    set_setting(ACTIVE_PROFILE_KEY, profile_id)
    from backend.app.knowledge.markdown import atomic_write
    from backend.app.knowledge.paths import knowledge_root

    atomic_write(knowledge_root() / "profiles" / "active-profile.txt", profile_id + "\n")
    return profile


def delete_profile(profile_id: str) -> None:
    if profile_id == DEFAULT_PROFILE_ID:
        raise ValueError("默认知识库不能删除。")
    if active_profile_id() == profile_id:
        switch_profile(DEFAULT_PROFILE_ID)
    with connect() as connection:
        connection.execute("DELETE FROM knowledge_profiles WHERE id = ?", (profile_id,))
    from backend.app.knowledge.paths import knowledge_root

    folder = _manifest_path(profile_id).parent
    if folder.exists():
        target = knowledge_root() / "trash" / "profiles" / profile_id
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(folder), str(target))


def link_source(source_id: str, profile_id: str | None = None) -> None:
    selected = profile_id or active_profile_id()
    with connect() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO knowledge_profile_sources(profile_id, source_id) VALUES (?, ?)",
            (selected, source_id),
        )
    sync_profile_manifest(selected)


def link_note(note_id: str, profile_id: str | None = None) -> None:
    selected = profile_id or active_profile_id()
    with connect() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO knowledge_profile_notes(profile_id, note_id) VALUES (?, ?)",
            (selected, note_id),
        )
    sync_profile_manifest(selected)
