from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


EntityType = Literal["concept", "person", "project", "tool", "method", "event", "note"]
Sensitivity = Literal["normal", "private", "secret"]
RelationType = Literal[
    "related_to",
    "depends_on",
    "used_by",
    "part_of",
    "contradicts",
    "supports",
]


class SourceFrontmatter(BaseModel):
    schema_version: int = 1
    id: str
    kind: Literal["source"] = "source"
    snapshot_id: str
    source_type: Literal["web", "file", "user"]
    canonical_uri: str | None = None
    title: str
    captured_at: str
    content_sha256: str
    language: str = "und"
    sensitivity: Sensitivity = "normal"
    capture_method: str
    browser_context_id: str | None = None
    status: Literal["active", "archived"] = "active"


class NoteFrontmatter(BaseModel):
    schema_version: int = 1
    id: str
    kind: Literal["note"] = "note"
    entity_type: EntityType
    title: str
    aliases: list[str] = Field(default_factory=list)
    status: Literal["draft", "active", "stale", "archived"] = "active"
    created_at: str
    updated_at: str
    source_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sensitivity: Sensitivity = "normal"
    generated_by: Literal["deskpilot", "user"] = "deskpilot"
    review_state: Literal["unreviewed", "reviewed", "pending"] = "unreviewed"
    manual_sections: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    source_id: str
    snapshot_id: str
    anchor: str
    reason: str = ""


class RelationItem(BaseModel):
    relation_type: RelationType = "related_to"
    target_note_id: str
    confidence: float = Field(default=1.0, ge=0, le=1)


class ProposalOperation(BaseModel):
    operation: Literal["create_note", "update_note", "add_relation", "mark_conflict", "no_change"]
    target_note_id: str | None = None
    entity_type: EntityType = "note"
    title: str = ""
    aliases: list[str] = Field(default_factory=list)
    summary: str = ""
    overview: str = ""
    details_markdown: str = ""
    tags: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    relations: list[RelationItem] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        return value.strip()


class CompilationProposal(BaseModel):
    source_id: str
    operations: list[ProposalOperation] = Field(default_factory=list)
    ignored_content: list[dict[str, str]] = Field(default_factory=list)


class KnowledgeSettings(BaseModel):
    enabled: bool = True
    auto_compile: bool = True
    review_updates: bool = True
    allow_private_remote: bool = False
    max_search_results: int = Field(default=8, ge=3, le=30)
    auto_create_notes: bool = True


class KnowledgeQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    mode: Literal["search", "answer", "explore", "compare", "timeline"] = "answer"
    limit: int | None = Field(default=None, ge=1, le=30)


class TextIngestRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    canonical_uri: str | None = None
    sensitivity: Sensitivity = "normal"
    compile: bool | None = None


class FileIngestRequest(BaseModel):
    path: str = Field(min_length=1, max_length=2000)
    sensitivity: Sensitivity = "normal"
    compile: bool | None = None
