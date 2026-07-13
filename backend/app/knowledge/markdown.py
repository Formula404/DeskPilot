from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml

from backend.app.knowledge.models import EvidenceItem, NoteFrontmatter, SourceFrontmatter
from backend.app.knowledge.paths import safe_knowledge_path

FRONTMATTER_BOUNDARY = "---"
SECTION_PATTERN = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def slugify(value: str, max_length: int = 70) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value, flags=re.UNICODE)
    return normalized.strip("-")[:max_length] or "untitled"


def normalize_title(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def parse_markdown_document(content: str) -> tuple[dict[str, Any], str]:
    if not content.startswith(FRONTMATTER_BOUNDARY + "\n"):
        raise ValueError("Markdown 缺少 YAML Frontmatter。")
    end = content.find("\n---\n", 4)
    if end < 0:
        raise ValueError("Markdown Frontmatter 未闭合。")
    raw = content[4:end]
    metadata = yaml.safe_load(raw) or {}
    if not isinstance(metadata, dict):
        raise ValueError("Markdown Frontmatter 必须是 object。")
    return metadata, content[end + 5 :]


def render_markdown_document(metadata: dict[str, Any], body: str) -> str:
    raw = yaml.safe_dump(
        metadata,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()
    return f"---\n{raw}\n---\n{body.rstrip()}\n"


def atomic_write(path: Path, content: str) -> None:
    target = safe_knowledge_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def split_sections(body: str) -> tuple[str, dict[str, str]]:
    matches = list(SECTION_PATTERN.finditer(body))
    if not matches:
        return body.strip(), {}
    preamble = body[: matches[0].start()].strip()
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[match.group(1).strip()] = body[match.end() : end].strip()
    return preamble, sections


def chunk_text(text: str, max_chars: int = 3500) -> list[tuple[str, str]]:
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for paragraph in paragraphs:
        if current and length + len(paragraph) + 2 > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            length = 0
        if len(paragraph) > max_chars:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                length = 0
            for start in range(0, len(paragraph), max_chars):
                chunks.append(paragraph[start : start + max_chars])
            continue
        current.append(paragraph)
        length += len(paragraph) + 2
    if current:
        chunks.append("\n\n".join(current))
    if not chunks and text.strip():
        chunks = [text.strip()]
    return [(f"chunk-{index:03d}", value) for index, value in enumerate(chunks, start=1)]


def render_source(frontmatter: SourceFrontmatter, content: str) -> str:
    blocks = []
    for anchor, chunk in chunk_text(content):
        blocks.append(f"<!-- chunk:{anchor} -->\n{chunk}")
    uri = frontmatter.canonical_uri or "local:user"
    body = (
        f"# {frontmatter.title}\n\n"
        "## Capture Metadata\n\n"
        f"- Original URI: {uri}\n"
        f"- Captured at: {frontmatter.captured_at}\n\n"
        "## Content\n\n"
        + "\n\n".join(blocks)
    )
    return render_markdown_document(frontmatter.model_dump(mode="json"), body)


def source_chunks(content: str) -> dict[str, str]:
    _, body = parse_markdown_document(content)
    _, sections = split_sections(body)
    source_body = sections.get("Content", "")
    pattern = re.compile(r"<!--\s*chunk:(chunk-\d+)\s*-->")
    matches = list(pattern.finditer(source_body))
    chunks: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source_body)
        chunks[match.group(1)] = source_body[match.end() : end].strip()
    return chunks


def render_note(
    frontmatter: NoteFrontmatter,
    *,
    summary: str,
    overview: str,
    details: str,
    evidence: list[EvidenceItem],
    relations: list[str] | None = None,
    open_questions: list[str] | None = None,
) -> str:
    evidence_lines = [
        f"- `{item.source_id}` / `{item.snapshot_id}#{item.anchor}`: {item.reason or '来源证据'}"
        for item in evidence
    ] or ["- 暂无来源证据。"]
    relation_lines = [f"- {item}" for item in relations or []] or ["- 暂无关系。"]
    question_lines = [f"- {item}" for item in open_questions or []] or ["- 暂无。"]
    body = (
        f"# {frontmatter.title}\n\n"
        f"## Summary\n\n{summary.strip()}\n\n"
        f"## Overview\n\n{overview.strip()}\n\n"
        f"## Details\n\n{details.strip()}\n\n"
        f"## Evidence\n\n{'\n'.join(evidence_lines)}\n\n"
        f"## Relations\n\n{'\n'.join(relation_lines)}\n\n"
        f"## Open Questions\n\n{'\n'.join(question_lines)}"
    )
    return render_markdown_document(frontmatter.model_dump(mode="json"), body)
