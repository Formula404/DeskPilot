from __future__ import annotations

from pathlib import Path

from backend.app.core.config import get_settings


def data_dir() -> Path:
    return get_settings().data_dir


def db_path() -> Path:
    return data_dir() / "deskpilot.sqlite3"


def ensure_data_dirs() -> None:
    root = data_dir()
    for relative in [
        "config",
        "exports",
        "logs",
        "screenshots",
        "tasks",
    ]:
        (root / relative).mkdir(parents=True, exist_ok=True)
