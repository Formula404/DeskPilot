from __future__ import annotations

from pathlib import Path


def capture_screen(path: Path) -> Path:
    import mss
    import mss.tools

    with mss.mss() as sct:
        monitor = sct.monitors[1]
        image = sct.grab(monitor)
        path.parent.mkdir(parents=True, exist_ok=True)
        mss.tools.to_png(image.rgb, image.size, output=str(path))
    return path
