from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from backend.app.core.paths import db_path
from backend.app.knowledge.paths import knowledge_root


def backup_database() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = knowledge_root() / "cache" / f"deskpilot-before-rebuild-{timestamp}.sqlite3"
    target.parent.mkdir(parents=True, exist_ok=True)
    if db_path().exists():
        shutil.copy2(db_path(), target)
    return target
