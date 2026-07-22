from __future__ import annotations

from pydantic import BaseModel


class ArtifactPathRequest(BaseModel):
    path: str
