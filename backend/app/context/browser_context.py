from __future__ import annotations

from backend.app.db.repository import get_latest_browser_context


def get_current_browser_context() -> dict | None:
    return get_latest_browser_context()
