from __future__ import annotations

import hashlib
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.app.core.config import get_settings
from backend.app.db.connection import connect, init_db
from backend.app.knowledge import compiler
from backend.app.knowledge.backup import KnowledgeBackupError, inspect_backup, restore_full_backup
from backend.app.knowledge.compiler import KnowledgeCompileError, compile_source, review_proposal
from backend.app.knowledge.paths import ensure_knowledge_dirs, from_knowledge_relative
from backend.app.knowledge.repository import get_source, list_proposals
from backend.app.knowledge.source_service import KnowledgeIngestError, ingest_content
from backend.app.main import app


@pytest.fixture
def isolated_knowledge(tmp_path):
    settings = get_settings()
    original = settings.data_dir
    settings.data_dir = tmp_path / "data"
    init_db()
    ensure_knowledge_dirs()
    try:
        yield settings.data_dir
    finally:
        settings.data_dir = original


def test_untrusted_host_and_websocket_origin_are_rejected(isolated_knowledge) -> None:
    client = TestClient(app)
    assert client.get("/health", headers={"host": "attacker.invalid"}).status_code == 400
    with pytest.raises(WebSocketDisconnect) as denied:
        with client.websocket_connect("/browser/ws", headers={"origin": "https://attacker.invalid"}):
            pass
    assert denied.value.code == 1008


def test_backup_rejects_zip_slip_paths(isolated_knowledge, tmp_path) -> None:
    archive = tmp_path / "malicious.zip"
    payload = b"owned"
    manifest = {
        "schema_version": 1,
        "files": [{"path": "vault/../../outside.txt", "sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}],
    }
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("manifest.json", json.dumps(manifest))
        bundle.writestr("vault/../../outside.txt", payload)
    with pytest.raises(KnowledgeBackupError):
        inspect_backup(archive)


def test_restore_revalidates_the_same_archive_handle_before_extraction(
    isolated_knowledge, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "swapped-malicious.zip"
    payload = b"owned"
    manifest = {
        "schema_version": 1,
        "files": [{"path": "vault/../../outside.txt", "sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}],
    }
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("manifest.json", json.dumps(manifest))
        bundle.writestr("vault/../../outside.txt", payload)

    # Simulates an earlier clean-path inspection being made irrelevant by an
    # archive replacement. Restore must not trust this separate inspection.
    monkeypatch.setattr("backend.app.knowledge.backup.inspect_backup", lambda _: {"path": str(archive), "valid": True})
    with pytest.raises(KnowledgeBackupError):
        restore_full_backup(archive)
    assert not (tmp_path / "outside.txt").exists()


def test_path_traversal_and_secret_content_are_blocked(isolated_knowledge) -> None:
    with pytest.raises(ValueError):
        from_knowledge_relative("../../outside.md")
    with pytest.raises(KnowledgeIngestError) as secret:
        ingest_content(source_type="user", title="Secret", content="api_key = super-secret-password-value-123456", canonical_uri="user://secret", capture_method="test")
    assert secret.value.code == "KNOWLEDGE_SECRET_DETECTED"


def test_concurrent_identical_ingest_is_idempotent(isolated_knowledge) -> None:
    def ingest():
        return ingest_content(source_type="web", title="Concurrent Source", content="The exact same sufficiently long body is submitted by many workers concurrently.", canonical_uri="https://example.com/concurrent?utm_source=test", capture_method="test")

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: ingest(), range(24)))
    assert sum(result["status"] == "created" for result in results) == 1
    assert {result["source_id"] for result in results} == {results[0]["source_id"]}
    with connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM knowledge_sources").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM knowledge_snapshots").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_concurrent_proposal_resolution_commits_once(isolated_knowledge, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(compiler, "get_settings", lambda: SimpleNamespace(openai_api_key=None, openai_base_url=None, openai_model="test"))
    source = ingest_content(source_type="web", title="Review Race", content="Initial source material long enough to create a stable knowledge page.", canonical_uri="https://example.com/review-race", capture_method="test")
    await compile_source(source["source_id"])
    ingest_content(source_type="web", title="Review Race", content="Updated source material that creates a guarded review proposal for concurrency testing.", canonical_uri="https://example.com/review-race", capture_method="test")
    proposal_id = (await compile_source(source["source_id"]))["pending"][0]["proposal_id"]

    def resolve():
        try:
            return review_proposal(proposal_id, "accept")["status"]
        except KnowledgeCompileError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: resolve(), range(8)))
    assert outcomes.count("accepted") == 1
    assert set(outcomes) <= {"accepted", "KNOWLEDGE_RESOURCE_BUSY", "KNOWLEDGE_PROPOSAL_RESOLVED"}
    assert not list_proposals()
