from __future__ import annotations

from pathlib import Path

from backend.app.context.screenshot import capture_screen


def screenshot(path: Path) -> Path:
    return capture_screen(path)
