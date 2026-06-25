from __future__ import annotations

from fastapi import APIRouter

from backend.app.context.current_window import get_foreground_window
from backend.app.db.repository import save_browser_context
from backend.app.schemas.tasks import BrowserContextRequest, BrowserContextResponse

router = APIRouter(prefix="/context", tags=["context"])


@router.get("/current-window")
def current_window() -> dict:
    return get_foreground_window()


@router.post("/browser/current-page", response_model=BrowserContextResponse)
def save_current_page(payload: BrowserContextRequest) -> BrowserContextResponse:
    context_id = save_browser_context(
        tab_id=str(payload.tab_id) if payload.tab_id is not None else None,
        url=payload.url,
        title=payload.title,
        visible_text=payload.visible_text,
        dom_summary=payload.dom_summary,
        captured_at=payload.captured_at,
    )
    return BrowserContextResponse(context_id=context_id)
