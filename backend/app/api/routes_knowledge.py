from __future__ import annotations

import json
import hashlib
import re
from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from backend.app.browser.bridge import browser_bridge
from backend.app.knowledge.backup import backup_database
from backend.app.knowledge.compiler import KnowledgeCompileError, compile_source, promote_answer, review_proposal
from backend.app.knowledge.indexer import read_indexed_note, rebuild_index
from backend.app.knowledge.lint import lint_knowledge, semantic_lint_knowledge
from backend.app.knowledge.markdown import atomic_write, parse_markdown_document, split_sections
from backend.app.knowledge.models import FileIngestRequest, KnowledgeProfileCreate, KnowledgeQueryRequest, KnowledgeSettings, TextIngestRequest
from backend.app.knowledge.paths import (
    ensure_knowledge_dirs,
    from_knowledge_relative,
    knowledge_root,
    purpose_path,
)
from backend.app.knowledge.repository import (
    count_notes,
    count_sources,
    get_note,
    get_proposal,
    get_snapshot,
    get_source,
    knowledge_counts,
    list_notes,
    list_proposals,
    list_sources,
    list_source_snapshots,
)
from backend.app.knowledge.retrieval import answer_knowledge, search_knowledge
from backend.app.knowledge.profiles import active_profile_id, create_profile, delete_profile, list_profiles, switch_profile
from backend.app.knowledge.settings import get_knowledge_settings, save_knowledge_settings
from backend.app.knowledge.source_service import KnowledgeIngestError, ingest_content, ingest_file
from backend.app.knowledge.document_parser import parse_document
from backend.app.knowledge.web_monitor import check_web_source, get_watch, list_watches, set_watch
from backend.app.knowledge.obsidian import export_obsidian_vault, obsidian_status
from backend.app.knowledge.storage import change_storage_directory, choose_storage_directory, open_storage_directory
from backend.app.knowledge.catalog import append_log, catalog_status, refresh_catalogs
from backend.app.knowledge.note_management import (
    KnowledgeNoteManagementError,
    delete_managed_note,
    update_managed_note,
)
from backend.app.tools.registry import tool_registry

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class KnowledgeSettingsUpdate(KnowledgeSettings):
    purpose: str = Field(default="", max_length=20000)


class ProposalResolution(BaseModel):
    decision: Literal["accept", "reject"]


class RebuildRequest(BaseModel):
    confirmed: bool = False


class WebWatchUpdate(BaseModel):
    enabled: bool = True
    interval_minutes: int | None = Field(default=None, ge=15, le=43200)


class KnowledgeNoteUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    entity_type: Literal["concept", "person", "project", "tool", "method", "event", "note"]
    summary: str = Field(default="", max_length=20000)
    overview: str = Field(default="", max_length=50000)
    details: str = Field(default="", max_length=200000)
    tags: list[str] = Field(default_factory=list, max_length=50)


class KnowledgeStorageUpdate(BaseModel):
    path: str = Field(min_length=1, max_length=2000)


class KnowledgePromotionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    answer: str = Field(min_length=1, max_length=100000)
    note_ids: list[str] = Field(min_length=1, max_length=50)


def _raise_domain_error(exc: Exception) -> None:
    code = getattr(exc, "code", "KNOWLEDGE_ERROR")
    status = 404 if code.endswith("NOT_FOUND") else 400
    raise HTTPException(status_code=status, detail={"code": code, "message": str(exc)}) from exc


@router.get("/status")
def knowledge_status() -> dict[str, Any]:
    ensure_knowledge_dirs()
    settings = get_knowledge_settings()
    return {
        **knowledge_counts(),
        "active_profile_id": active_profile_id(),
        "enabled": settings.enabled,
        "browser_connected": browser_bridge.is_connected,
        "root_path": str(knowledge_root().resolve()),
    }


@router.get("/settings")
def knowledge_settings() -> dict[str, Any]:
    ensure_knowledge_dirs()
    return {
        **get_knowledge_settings().model_dump(),
        "purpose": purpose_path().read_text(encoding="utf-8"),
        "root_path": str(knowledge_root().resolve()),
        "active_profile_id": active_profile_id(),
    }


@router.post("/storage/choose")
def choose_knowledge_storage() -> dict[str, Any]:
    try:
        selected = choose_storage_directory()
        return {"path": selected, "cancelled": selected is None}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/storage")
def update_knowledge_storage(payload: KnowledgeStorageUpdate) -> dict[str, Any]:
    try:
        return change_storage_directory(payload.path)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/storage/open")
def open_knowledge_storage() -> dict[str, bool]:
    try:
        open_storage_directory()
    except OSError as exc:
        raise HTTPException(status_code=500, detail="无法打开知识库目录") from exc
    return {"ok": True}


@router.get("/profiles")
def knowledge_profiles() -> dict[str, Any]:
    return {"items": list_profiles(), "active_profile_id": active_profile_id()}


@router.get("/obsidian/status")
def knowledge_obsidian_status() -> dict[str, Any]:
    return obsidian_status()


@router.get("/catalog")
def knowledge_catalog() -> dict[str, Any]:
    refresh_catalogs()
    return catalog_status()


@router.post("/promote")
def promote_knowledge_answer(payload: KnowledgePromotionRequest) -> dict[str, Any]:
    try:
        return promote_answer(payload.title, payload.answer, payload.note_ids)
    except KnowledgeCompileError as exc:
        _raise_domain_error(exc)


@router.post("/lint/semantic")
async def semantic_lint() -> dict[str, Any]:
    return await semantic_lint_knowledge()


@router.post("/obsidian/export")
def export_knowledge_to_obsidian() -> dict[str, Any]:
    try:
        return export_obsidian_vault()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/profiles")
def create_knowledge_profile(payload: KnowledgeProfileCreate) -> dict[str, Any]:
    return create_profile(payload.name, payload.description)


@router.post("/profiles/{profile_id}/activate")
def activate_knowledge_profile(profile_id: str) -> dict[str, Any]:
    try:
        return switch_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/profiles/{profile_id}")
def remove_knowledge_profile(profile_id: str) -> dict[str, bool]:
    try:
        delete_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.put("/settings")
def update_knowledge_settings(payload: KnowledgeSettingsUpdate) -> dict[str, Any]:
    ensure_knowledge_dirs()
    settings = KnowledgeSettings.model_validate(payload.model_dump(exclude={"purpose"}))
    save_knowledge_settings(settings)
    purpose = payload.purpose.strip()
    if purpose:
        atomic_write(purpose_path(), purpose + "\n")
    return {**settings.model_dump(), "purpose": purpose_path().read_text(encoding="utf-8")}


@router.get("/notes")
def knowledge_notes(
    query: str | None = None,
    entity_type: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    items = list_notes(query=query, entity_type=entity_type, status=status, limit=limit, offset=offset)
    total = count_notes(query=query, entity_type=entity_type, status=status)
    return {"items": items, "count": len(items), "total": total, "offset": offset}


@router.get("/notes/{note_id}")
def knowledge_note_detail(note_id: str) -> dict[str, Any]:
    note = get_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Knowledge note not found")
    frontmatter, sections, content = read_indexed_note(note)
    return {
        **note,
        "frontmatter": frontmatter.model_dump(mode="json"),
        "sections": sections,
        "content": content,
    }


@router.put("/notes/{note_id}")
def update_knowledge_note(note_id: str, payload: KnowledgeNoteUpdate) -> dict[str, Any]:
    try:
        update_managed_note(note_id, payload.model_dump())
        return knowledge_note_detail(note_id)
    except KnowledgeNoteManagementError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/notes/{note_id}")
def delete_knowledge_note(note_id: str) -> dict[str, Any]:
    try:
        return delete_managed_note(note_id)
    except KnowledgeNoteManagementError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/sources/{source_id}")
def knowledge_source_detail(source_id: str) -> dict[str, Any]:
    source = get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    snapshots = list_source_snapshots(source_id)
    return {**source, "snapshots": snapshots, "watch": get_watch(source_id) if source.get("source_type") == "web" else None}


@router.get("/sources")
def knowledge_sources(
    query: str | None = None,
    source_type: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    items = list_sources(
        query=query,
        source_type=source_type,
        status=status,
        limit=limit,
        offset=offset,
    )
    total = count_sources(query=query, source_type=source_type, status=status)
    return {"items": items, "count": len(items), "total": total, "offset": offset}


@router.get("/snapshots/{snapshot_id}")
def knowledge_snapshot_detail(snapshot_id: str) -> dict[str, Any]:
    snapshot = get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Knowledge snapshot not found")
    path = from_knowledge_relative(str(snapshot["markdown_path"]))
    content = path.read_text(encoding="utf-8")
    metadata, body = parse_markdown_document(content)
    _, sections = split_sections(body)
    return {**snapshot, "frontmatter": metadata, "sections": sections, "content": content}


@router.post("/ingest/current-page")
async def ingest_current_page(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    result = await tool_registry.call("knowledge.ingest_current_page", payload or {})
    if not result.ok:
        raise HTTPException(
            status_code=400,
            detail={
                "code": result.error.code if result.error else "KNOWLEDGE_INGEST_FAILED",
                "message": result.message,
            },
        )
    return result.data or {}


@router.post("/ingest/text")
async def ingest_text(payload: TextIngestRequest) -> dict[str, Any]:
    try:
        if not get_knowledge_settings().enabled:
            raise KnowledgeIngestError("知识库已在设置中停用。", "KNOWLEDGE_DISABLED")
        result = ingest_content(
            source_type="user",
            title=payload.title,
            content=payload.content,
            canonical_uri=payload.canonical_uri,
            sensitivity=payload.sensitivity,
            capture_method="user_input",
        )
        should_compile = payload.compile
        if should_compile is None:
            should_compile = get_knowledge_settings().auto_compile
        if should_compile and result["status"] != "already_exists":
            result["compilation"] = await compile_source(result["source_id"])
        return result
    except (KnowledgeIngestError, KnowledgeCompileError) as exc:
        _raise_domain_error(exc)


@router.post("/ingest/file")
async def ingest_local_file(payload: FileIngestRequest) -> dict[str, Any]:
    try:
        if not get_knowledge_settings().enabled:
            raise KnowledgeIngestError("知识库已在设置中停用。", "KNOWLEDGE_DISABLED")
        result = ingest_file(payload.path, sensitivity=payload.sensitivity)
        should_compile = payload.compile
        if should_compile is None:
            should_compile = get_knowledge_settings().auto_compile
        if should_compile and result["status"] != "already_exists":
            result["compilation"] = await compile_source(result["source_id"])
        return result
    except (KnowledgeIngestError, KnowledgeCompileError) as exc:
        _raise_domain_error(exc)


@router.post("/ingest/upload")
async def ingest_uploaded_file(
    file: UploadFile = File(...),
    sensitivity: str = Form(default="normal"),
    compile: bool = Form(default=True),
) -> dict[str, Any]:
    if sensitivity not in {"normal", "private"}:
        raise HTTPException(status_code=400, detail="Invalid sensitivity")
    safe_name = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "-", file.filename or "upload")[:120]
    content = await file.read(100 * 1024 * 1024 + 1)
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 100 MB")
    temporary = knowledge_root() / "cache" / "imports" / safe_name
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_bytes(content)
    try:
        parsed = parse_document(temporary)
        digest = hashlib.sha256(content).hexdigest()
        result = ingest_content(
            source_type="file",
            title=parsed.title,
            content=parsed.content,
            canonical_uri=f"upload://{safe_name}?sha256={digest}",
            sensitivity=sensitivity,
            capture_method=parsed.capture_method,
            metadata={"original_filename": file.filename, "size_bytes": len(content), **parsed.metadata},
        )
        if compile and result["status"] != "already_exists":
            result["compilation"] = await compile_source(result["source_id"])
        return result
    except (ValueError, KnowledgeIngestError, KnowledgeCompileError) as exc:
        _raise_domain_error(exc)
    finally:
        temporary.unlink(missing_ok=True)


@router.post("/query")
async def query_knowledge(payload: KnowledgeQueryRequest) -> dict[str, Any]:
    if not get_knowledge_settings().enabled:
        raise HTTPException(status_code=400, detail={"code": "KNOWLEDGE_DISABLED", "message": "知识库已停用。"})
    if payload.mode == "search":
        results = search_knowledge(payload.query, payload.limit)
        append_log("query", payload.query, f"Search returned {len(results)} pages.")
        return {"query": payload.query, "results": results, "answer": None}
    return await answer_knowledge(payload.query, payload.limit)


@router.post("/sources/{source_id}/compile")
async def compile_knowledge_source(source_id: str) -> dict[str, Any]:
    try:
        return await compile_source(source_id)
    except KnowledgeCompileError as exc:
        _raise_domain_error(exc)


@router.post("/notes/{note_id}/refresh")
async def refresh_knowledge_note(note_id: str) -> dict[str, Any]:
    note = get_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Knowledge note not found")
    source_ids = list(dict.fromkeys(str(item["source_id"]) for item in note.get("sources", [])))
    if not source_ids:
        raise HTTPException(status_code=400, detail="该知识页面没有可用于更新的来源")
    try:
        results = [await compile_source(source_id, note_id) for source_id in source_ids]
        return {"note_id": note_id, "results": results, "pending": [proposal for result in results for proposal in result.get("pending", [])]}
    except KnowledgeCompileError as exc:
        _raise_domain_error(exc)


@router.get("/watches")
def knowledge_watches() -> dict[str, Any]:
    items = list_watches()
    return {"items": items, "count": len(items)}


@router.put("/sources/{source_id}/watch")
def update_source_watch(source_id: str, payload: WebWatchUpdate) -> dict[str, Any]:
    source = get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    if source.get("source_type") != "web":
        raise HTTPException(status_code=400, detail="Only web sources can be watched")
    if payload.enabled:
        current_settings = get_knowledge_settings()
        if not current_settings.web_update_enabled:
            save_knowledge_settings(current_settings.model_copy(update={"web_update_enabled": True}))
    return set_watch(source_id, payload.enabled, payload.interval_minutes)


@router.post("/sources/{source_id}/check-update")
async def check_source_update(source_id: str) -> dict[str, Any]:
    try:
        return await check_web_source(source_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/proposals")
def knowledge_proposals(status: str = "pending") -> dict[str, Any]:
    items = list_proposals(status)
    return {"items": items, "count": len(items)}


@router.get("/proposals/{proposal_id}")
def knowledge_proposal_detail(proposal_id: str) -> dict[str, Any]:
    proposal = get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Knowledge proposal not found")
    path = from_knowledge_relative(str(proposal["proposal_path"]))
    payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    target_note = None
    if proposal.get("target_note_id"):
        note = get_note(str(proposal["target_note_id"]))
        if note:
            frontmatter, sections, _ = read_indexed_note(note)
            target_note = {
                **note,
                "frontmatter": frontmatter.model_dump(mode="json"),
                "sections": sections,
            }
    return {**proposal, "payload": payload, "target_note": target_note}


@router.post("/proposals/{proposal_id}/resolve")
def resolve_knowledge_proposal(proposal_id: str, payload: ProposalResolution) -> dict[str, Any]:
    try:
        return review_proposal(proposal_id, payload.decision)
    except KnowledgeCompileError as exc:
        _raise_domain_error(exc)


@router.post("/lint")
def run_knowledge_lint() -> dict[str, Any]:
    return lint_knowledge()


@router.post("/rebuild-index")
def rebuild_knowledge_index(payload: RebuildRequest) -> dict[str, Any]:
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="Index rebuild requires confirmation")
    backup = backup_database()
    result = rebuild_index()
    return {"backup_path": str(backup), **result}
