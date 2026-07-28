from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.app.browser.bridge import BrowserBridgeError, browser_bridge
from backend.app.personal_info.service import (
    CATEGORIES, RECORD_CATEGORIES, create_form_session, delete_field, delete_form_memory,
    delete_record, delete_record_field, finalize_form_session, list_fields, list_form_memories,
    get_form_session, list_records, resolve_form_session, update_field, update_form_memory, update_record_field,
    upsert_field, upsert_record,
)

router = APIRouter(prefix="/personal-info", tags=["personal-info"])

class PersonalInfoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str = "other"
    field_key: str
    label: str
    value: str
    aliases: list[str] = Field(default_factory=list)

class PersonalInfoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str | None = None
    field_key: str | None = None
    label: str | None = None
    value: str | None = None
    aliases: list[str] | None = None
    status: str | None = None

class RecordFieldUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str
    label: str | None = None

class RecordFieldCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_key: str
    label: str
    value: str
    aliases: list[str] = Field(default_factory=list)

class PersonalInfoRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str
    fields: list[RecordFieldCreate] = Field(min_length=1, max_length=30)

class FormMemoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_key: str | None = None
    action: str | None = None
    source_field_id: str | None = None
    source_record_id: str | None = None
    override_value: str | None = None
    priority: int | None = None

class FormFieldChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str | None = None
    value: str | None = Field(default=None, max_length=5000)
    replace_existing: bool = False
    remember: bool | None = None
    save_to_profile: bool = False

class FormSessionApply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    groups: dict[str, str] = Field(default_factory=dict)
    fields: dict[str, FormFieldChoice] = Field(default_factory=dict)
    remember: bool = False
    apply_ready: bool = True

@router.get("")
def get_personal_info() -> dict[str, Any]:
    return {"categories": CATEGORIES, "record_categories": sorted(RECORD_CATEGORIES),
            "items": list_fields(), "records": list_records(), "form_memories": list_form_memories()}

@router.post("", status_code=201)
def create_personal_info(payload: PersonalInfoCreate) -> dict[str, Any]:
    try:
        return upsert_field(**payload.model_dump(), source_type="user_edit", status="confirmed")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("/records", status_code=201)
def create_personal_info_record(payload: PersonalInfoRecordCreate) -> dict[str, Any]:
    try:
        return upsert_record(category=payload.category,
                             fields=[item.model_dump() for item in payload.fields],
                             source_type="user_edit", source_ref=None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get("/form-memories")
def get_form_memories() -> dict[str, Any]:
    return {"items": list_form_memories()}

@router.put("/form-memories/{memory_id}")
def edit_form_memory(memory_id: str, payload: FormMemoryUpdate) -> dict[str, Any]:
    try:
        result = update_form_memory(memory_id, payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="Form fill memory not found")
    return result

@router.delete("/form-memories/{memory_id}")
def remove_form_memory(memory_id: str) -> dict[str, bool]:
    if not delete_form_memory(memory_id):
        raise HTTPException(status_code=404, detail="Form fill memory not found")
    return {"ok": True}

@router.post("/form-sessions/current", status_code=201)
async def preview_current_form() -> dict[str, Any]:
    try:
        page = await browser_bridge.inspect_form()
        return create_form_session(page)
    except BrowserBridgeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@router.get("/form-sessions/{session_id}")
def read_form_session(session_id: str) -> dict[str, Any]:
    session = get_form_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Form fill session not found or expired")
    return session["plan"]

@router.post("/form-sessions/{session_id}/apply")
async def apply_form_session(session_id: str, payload: FormSessionApply) -> dict[str, Any]:
    try:
        resolved = resolve_form_session(session_id, payload.model_dump())
        session = resolved["session"]
        assignments = resolved["assignments"]
        if not assignments:
            plan = finalize_form_session(session_id, resolved["resolutions"], [])
            return {"filled_count": 0, "filled": [], "skipped": [], "submitted": False,
                    "form_session": plan}
        stored_tab = session.get("tab_id")
        target_tab = int(stored_tab) if str(stored_tab or "").isdigit() else stored_tab
        target = {"tab": target_tab, "url": session["url"],
                  "document_id": session.get("document_id"), "strict_document": True}
        result = await browser_bridge.fill_form(assignments, target=target)
        plan = finalize_form_session(session_id, resolved["resolutions"], list(result.get("filled") or []))
        return {**result, "form_session": plan, "submitted": False}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BrowserBridgeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@router.put("/{field_id}")
def edit_personal_info(field_id: str, payload: PersonalInfoUpdate) -> dict[str, Any]:
    try:
        result = update_field(field_id, payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="Personal information field not found")
    return result

@router.delete("/{field_id}")
def remove_personal_info(field_id: str) -> dict[str, bool]:
    if not delete_field(field_id):
        raise HTTPException(status_code=404, detail="Personal information field not found")
    return {"ok": True}

@router.put("/records/{record_id}/fields/{field_key}")
def edit_record_field(record_id: str, field_key: str, payload: RecordFieldUpdate) -> dict[str, Any]:
    try:
        result = update_record_field(record_id, field_key, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="Personal information record field not found")
    return result

@router.delete("/records/{record_id}")
def remove_record(record_id: str) -> dict[str, bool]:
    if not delete_record(record_id):
        raise HTTPException(status_code=404, detail="Personal information record not found")
    return {"ok": True}

@router.delete("/records/{record_id}/fields/{field_key}")
def remove_record_field(record_id: str, field_key: str) -> dict[str, bool]:
    if not delete_record_field(record_id, field_key):
        raise HTTPException(status_code=404, detail="Personal information record field not found")
    return {"ok": True}
