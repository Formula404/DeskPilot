from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.db.repository import (
    create_session,
    delete_session,
    get_session,
    list_messages,
    update_session,
)
from backend.app.schemas.context import SessionCreateRequest, SessionResponse


router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse)
def new_session(payload: SessionCreateRequest) -> SessionResponse:
    session_id = create_session(source=payload.source, title=payload.title)
    return SessionResponse(session_id=session_id)


@router.get("/{session_id}")
def session_detail(session_id: str) -> dict:
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {**session, "messages": list_messages(session_id, limit=50)}


@router.post("/{session_id}/archive")
def archive_session(session_id: str) -> dict[str, bool]:
    if not get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    update_session(session_id, status="archived")
    return {"ok": True}


@router.delete("/{session_id}")
def remove_session(session_id: str) -> dict[str, bool]:
    if not delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}

