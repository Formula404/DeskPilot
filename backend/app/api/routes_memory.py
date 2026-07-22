from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.memory.repository import delete_memory, list_memories


router = APIRouter(prefix="/memories", tags=["memory"])


@router.get("")
def memories() -> dict:
    return {"items": list_memories()}


@router.delete("/{memory_id}")
def remove_memory(memory_id: str) -> dict[str, bool]:
    if not delete_memory(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}
