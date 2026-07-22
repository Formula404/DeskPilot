from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.artifacts import service
from backend.app.api import routes_artifacts
from backend.app.main import app


def configure_roots(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(service, "data_dir", lambda: root)
    monkeypatch.setattr(service, "knowledge_root", lambda: root / "knowledge")


def test_resolve_artifact_file_allows_generated_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    configure_roots(monkeypatch, tmp_path)
    artifact = tmp_path / "exports" / "report.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("ok", encoding="utf-8")

    assert service.resolve_artifact_file(str(artifact)) == artifact.resolve()


def test_resolve_artifact_file_rejects_path_outside_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside.txt"
    allowed.mkdir()
    outside.write_text("no", encoding="utf-8")
    configure_roots(monkeypatch, allowed)

    with pytest.raises(ValueError, match="DeskPilot"):
        service.resolve_artifact_file(str(outside))


def test_resolve_artifact_file_rejects_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    configure_roots(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="不存在"):
        service.resolve_artifact_file(str(tmp_path / "missing.xlsx"))


def test_open_artifact_route_returns_resolved_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    artifact = tmp_path / "report.xlsx"
    artifact.write_bytes(b"xlsx")
    monkeypatch.setattr(routes_artifacts, "open_artifact", lambda path: artifact.resolve())

    response = TestClient(app).post("/artifacts/open", json={"path": str(artifact)})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "path": str(artifact.resolve())}
