from __future__ import annotations

from pathlib import Path


def load_image(path: Path):
    import cv2

    return cv2.imread(str(path))
