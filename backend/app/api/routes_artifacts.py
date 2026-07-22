from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.artifacts.service import open_artifact, reveal_artifact
from backend.app.schemas.artifacts import ArtifactPathRequest

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.post("/open")
def open_artifact_file(payload: ArtifactPathRequest) -> dict[str, str | bool]:
    try:
        target = open_artifact(payload.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="无法使用系统默认应用打开文件。") from exc
    return {"ok": True, "path": str(target)}


@router.post("/reveal")
def reveal_artifact_file(payload: ArtifactPathRequest) -> dict[str, str | bool]:
    try:
        target = reveal_artifact(payload.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="无法在文件资源管理器中显示文件。") from exc
    return {"ok": True, "path": str(target)}
