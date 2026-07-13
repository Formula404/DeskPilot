from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from backend.app.db.repository import new_id, now_iso
from backend.app.knowledge.indexer import index_source_path
from backend.app.knowledge.document_parser import parse_document
from backend.app.knowledge.markdown import atomic_write, render_source, sha256_text
from backend.app.knowledge.models import Sensitivity, SourceFrontmatter
from backend.app.knowledge.paths import ensure_knowledge_dirs, knowledge_root, relative_to_knowledge
from backend.app.knowledge.repository import (
    create_snapshot,
    create_source,
    get_snapshot_by_hash,
    get_source_by_uri,
    mark_source_notes_stale,
    update_source,
)

TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src"}
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:api[_-]?key|access[_-]?token|password)\s*[:=]\s*[^\s]{8,}", re.IGNORECASE),
]


class KnowledgeIngestError(RuntimeError):
    def __init__(self, message: str, code: str = "KNOWLEDGE_INGEST_FAILED") -> None:
        super().__init__(message)
        self.code = code


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise KnowledgeIngestError("来源 URL 无效。", "KNOWLEDGE_INVALID_URL")
    hostname = (parsed.hostname or "").lower()
    port = f":{parsed.port}" if parsed.port and parsed.port not in {80, 443} else ""
    netloc = hostname + port
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMETERS
    ]
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, urlencode(query), ""))


def detect_secret(content: str) -> bool:
    sample = content[:100000]
    return any(pattern.search(sample) for pattern in SECRET_PATTERNS)


def _source_path(source_type: str, source_id: str, snapshot_id: str, captured_at: str):
    root = knowledge_root() / "sources" / source_type
    if source_type == "web":
        try:
            instant = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        except ValueError:
            instant = datetime.now(UTC)
        root = root / f"{instant.year:04d}" / f"{instant.month:02d}"
    return root / f"{source_id}--{snapshot_id[-8:]}.md"


def ingest_content(
    *,
    source_type: str,
    title: str,
    content: str,
    canonical_uri: str | None,
    sensitivity: Sensitivity = "normal",
    capture_method: str,
    captured_at: str | None = None,
    browser_context_id: str | None = None,
    metadata: dict | None = None,
) -> dict:
    ensure_knowledge_dirs()
    clean_title = title.strip() or "Untitled source"
    clean_content = content.strip()
    if len(clean_content) < 20:
        raise KnowledgeIngestError("来源正文过短，无法形成有效知识来源。", "KNOWLEDGE_CONTENT_TOO_SHORT")
    if sensitivity == "secret" or detect_secret(clean_content):
        raise KnowledgeIngestError(
            "内容中检测到疑似密钥或秘密信息，已阻止写入知识库。",
            "KNOWLEDGE_SECRET_DETECTED",
        )

    uri = canonicalize_url(canonical_uri) if source_type == "web" and canonical_uri else canonical_uri
    if not uri:
        uri = f"{source_type}://{new_id()}"
    source = get_source_by_uri(source_type, uri)
    is_new_source = source is None
    if source is None:
        source = create_source(
            source_type=source_type,
            canonical_uri=uri,
            title=clean_title,
            sensitivity=sensitivity,
        )
        # A globally deduplicated source may already have snapshots from another profile.
        is_new_source = not bool(source.get("current_snapshot_id"))

    source_id = str(source["id"])
    content_hash = sha256_text(clean_content)
    duplicate = get_snapshot_by_hash(source_id, content_hash)
    if duplicate:
        return {
            "status": "already_exists",
            "source_id": source_id,
            "snapshot_id": duplicate["id"],
            "path": duplicate["markdown_path"],
            "title": clean_title,
            "is_new_source": False,
        }

    snapshot_id = f"snap_{new_id().replace('-', '')}"
    captured = captured_at or now_iso()
    path = _source_path(source_type, source_id, snapshot_id, captured)
    frontmatter = SourceFrontmatter(
        id=source_id,
        snapshot_id=snapshot_id,
        source_type=source_type,
        canonical_uri=uri,
        title=clean_title,
        captured_at=captured,
        content_sha256=content_hash,
        language="zh-CN" if re.search(r"[\u4e00-\u9fff]", clean_content) else "und",
        sensitivity=sensitivity,
        capture_method=capture_method,
        browser_context_id=browser_context_id,
    )
    atomic_write(path, render_source(frontmatter, clean_content))
    relative_path = relative_to_knowledge(path)
    create_snapshot(
        snapshot_id=snapshot_id,
        source_id=source_id,
        content_sha256=content_hash,
        markdown_path=relative_path,
        browser_context_id=browser_context_id,
        captured_at=captured,
        metadata=metadata or {},
    )
    was_update = not is_new_source and bool(source.get("current_snapshot_id"))
    if was_update:
        mark_source_notes_stale(source_id)
    update_source(
        source_id,
        title=clean_title,
        current_snapshot_id=snapshot_id,
        status="updated" if was_update else "active",
    )
    index_source_path(path)
    if source_type == "web":
        from backend.app.knowledge.settings import get_knowledge_settings

        if get_knowledge_settings().auto_watch_web_sources:
            from backend.app.knowledge.web_monitor import set_watch
            from backend.app.knowledge.web_monitor import get_watch

            if not get_watch(source_id):
                set_watch(source_id, True)
    return {
        "status": "updated" if was_update else "created",
        "source_id": source_id,
        "snapshot_id": snapshot_id,
        "path": relative_path,
        "title": clean_title,
        "is_new_source": is_new_source,
    }


def ingest_file(path_value: str, *, sensitivity: Sensitivity = "normal") -> dict:
    path = Path(path_value).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise KnowledgeIngestError("要导入的文件不存在。", "KNOWLEDGE_FILE_NOT_FOUND")
    supported = {".md", ".txt", ".pdf", ".docx", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
    if path.suffix.lower() not in supported:
        raise KnowledgeIngestError(
            "当前支持 Markdown、TXT、PDF、DOCX 和常见图片文件。",
            "KNOWLEDGE_FILE_TYPE_UNSUPPORTED",
        )
    if path.stat().st_size > 100 * 1024 * 1024:
        raise KnowledgeIngestError("文件超过 100 MB 导入上限。", "KNOWLEDGE_FILE_TOO_LARGE")
    try:
        parsed = parse_document(path)
    except Exception as exc:
        raise KnowledgeIngestError(str(exc), "KNOWLEDGE_FILE_PARSE_FAILED") from exc
    return ingest_content(
        source_type="file",
        title=parsed.title,
        content=parsed.content,
        canonical_uri=path.as_uri(),
        sensitivity=sensitivity,
        capture_method=parsed.capture_method,
        metadata={"original_path": str(path), "size_bytes": path.stat().st_size, **parsed.metadata},
    )
