from __future__ import annotations

from fastapi import APIRouter

from backend.app.context.current_window import get_foreground_window
from backend.app.context.service import runtime_context_service
from backend.app.api.events import event_bus
from backend.app.db.repository import (
    cleanup_expired_context,
    delete_context_snapshot,
    get_context_snapshot,
    list_context_snapshots,
    list_sessions,
    save_browser_context,
)
from backend.app.schemas.context import SnapshotRequest, SnapshotResponse
from backend.app.schemas.tasks import BrowserContextRequest, BrowserContextResponse

router = APIRouter(prefix="/context", tags=["context"])


@router.post("/snapshots", response_model=SnapshotResponse)
async def create_snapshot(payload: SnapshotRequest) -> SnapshotResponse:
    result = await runtime_context_service.create_snapshot(
        session_id=payload.session_id,
        source=payload.source,
        include=list(payload.include),
        attachments=payload.attachments,
        sensitivity=payload.sensitivity,
    )
    await event_bus.publish(
        "context.snapshot.created",
        "已冻结提交时上下文",
        payload={
            "context_snapshot_id": result["context_snapshot_id"],
            "available": result["available"],
            "degraded_reasons": result["degraded_reasons"],
        },
    )
    return SnapshotResponse(**result)


@router.get("/snapshots/{snapshot_id}")
def snapshot_detail(snapshot_id: str) -> dict:
    snapshot = get_context_snapshot(snapshot_id)
    if not snapshot:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Context snapshot not found")
    return snapshot


@router.delete("/snapshots/{snapshot_id}")
def remove_snapshot(snapshot_id: str) -> dict[str, bool]:
    return {"ok": delete_context_snapshot(snapshot_id)}


@router.post("/cleanup")
def cleanup_context() -> dict[str, int]:
    return cleanup_expired_context()


@router.get("/data")
def context_data() -> dict:
    sessions = list_sessions()
    snapshots = list_context_snapshots()
    return {
        "sessions": sessions,
        "snapshots": snapshots,
        "counts": {"sessions": len(sessions), "snapshots": len(snapshots)},
    }


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
