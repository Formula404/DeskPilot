from __future__ import annotations

from fastapi import APIRouter, HTTPException
from openai import AsyncOpenAI

from backend.app.settings.models import ApplicationSettingsUpdate, PublicApplicationSettings
from backend.app.settings.service import get_public_settings, get_runtime_settings, save_application_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=PublicApplicationSettings)
def get_settings() -> PublicApplicationSettings:
    return get_public_settings()


@router.put("", response_model=PublicApplicationSettings)
def update_settings(payload: ApplicationSettingsUpdate) -> PublicApplicationSettings:
    return save_application_settings(payload)


@router.post("/ai/test")
async def test_ai_connection() -> dict[str, str | bool]:
    settings = get_runtime_settings().ai
    if not settings.api_key:
        raise HTTPException(status_code=400, detail="请先填写并保存 API Key")
    try:
        client = AsyncOpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.request_timeout_seconds,
        )
        await client.models.list()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"模型服务连接失败：{exc}") from exc
    return {"ok": True, "message": "模型服务连接成功"}
