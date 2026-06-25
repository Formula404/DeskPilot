from __future__ import annotations


def requires_approval(risk_level: str) -> bool:
    return risk_level in {"medium", "high"}
