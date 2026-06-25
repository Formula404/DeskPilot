from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings() -> dict:
    return {"settings": {}}


@router.post("")
def update_settings(payload: dict) -> dict:
    return {"ok": True, "settings": payload}
