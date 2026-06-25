from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache
def _engine():
    from paddleocr import PaddleOCR

    return PaddleOCR(use_angle_cls=True, lang="ch")


def ocr_image(path: Path) -> list[dict]:
    result = _engine().ocr(str(path), cls=True)
    items: list[dict] = []
    for line in result[0] if result else []:
        box, text_info = line
        text, confidence = text_info
        items.append({"box": box, "text": text, "confidence": confidence})
    return items
