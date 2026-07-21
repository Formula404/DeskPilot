from __future__ import annotations

import asyncio

from backend.app.browser.bridge import BrowserBridgeError, browser_bridge
from backend.app.db.repository import now_iso, save_browser_context
from backend.app.knowledge.backup import backup_database
from backend.app.knowledge.compiler import KnowledgeCompileError, compile_source, review_proposal
from backend.app.knowledge.indexer import rebuild_index
from backend.app.knowledge.lint import lint_knowledge, semantic_lint_knowledge
from backend.app.knowledge.models import FileIngestRequest, TextIngestRequest
from backend.app.knowledge.paths import knowledge_root
from backend.app.knowledge.retrieval import answer_knowledge, search_knowledge
from backend.app.knowledge.settings import get_knowledge_settings
from backend.app.knowledge.source_service import KnowledgeIngestError, ingest_content, ingest_file
from backend.app.schemas.common import Artifact, ToolError, ToolResult
from backend.app.tools.base import ToolDefinition


def _failure(exc: Exception, fallback_code: str) -> ToolResult:
    return ToolResult(
        ok=False,
        message=str(exc),
        error=ToolError(code=getattr(exc, "code", fallback_code)),
    )


async def _ingest_current_page(payload: dict) -> ToolResult:
    try:
        if not get_knowledge_settings().enabled:
            raise KnowledgeIngestError("知识库已在设置中停用。", "KNOWLEDGE_DISABLED")
        page = await browser_bridge.collect_page()
        url = page.get("url")
        if not isinstance(url, str) or not url:
            raise KnowledgeIngestError("浏览器扩展未返回有效 URL。", "KNOWLEDGE_INVALID_URL")
        text = str(page.get("content_text") or page.get("visible_text") or "")
        context_id = save_browser_context(
            tab_id=str(page.get("tab_id")) if page.get("tab_id") is not None else None,
            url=url,
            title=page.get("title"),
            visible_text=text,
            dom_summary=page.get("dom_summary") or [],
            captured_at=page.get("captured_at") or now_iso(),
        )
        result = ingest_content(
            source_type="web",
            title=str(page.get("title") or url),
            content=text,
            canonical_uri=url,
            sensitivity=payload.get("sensitivity", "normal"),
            capture_method="browser_extension",
            captured_at=page.get("captured_at") or now_iso(),
            browser_context_id=context_id,
            metadata={"tab_id": page.get("tab_id"), "dom_summary": page.get("dom_summary") or [], "page_metadata": page.get("metadata") or {}, "extraction_method": page.get("extraction_method"), "content_quality": page.get("content_quality"), "headings": page.get("headings") or [], "json_ld": page.get("json_ld") or []},
        )
        should_compile = payload.get("compile")
        if should_compile is None:
            should_compile = get_knowledge_settings().auto_compile
        compilation = None
        if should_compile and result["status"] != "already_exists":
            compilation = await compile_source(result["source_id"])
        data = {**result, "compilation": compilation}
        artifacts = [Artifact(type="knowledge_source", path=str(knowledge_root() / result["path"]))]
        return ToolResult(ok=True, data=data, message="当前网页已加入知识库", artifacts=artifacts)
    except (BrowserBridgeError, KnowledgeIngestError, KnowledgeCompileError) as exc:
        return _failure(exc, "KNOWLEDGE_INGEST_FAILED")


async def _ingest_text(payload: dict) -> ToolResult:
    try:
        if not get_knowledge_settings().enabled:
            raise KnowledgeIngestError("知识库已在设置中停用。", "KNOWLEDGE_DISABLED")
        request = TextIngestRequest.model_validate(payload)
        result = ingest_content(
            source_type="user",
            title=request.title,
            content=request.content,
            canonical_uri=request.canonical_uri,
            sensitivity=request.sensitivity,
            capture_method="user_input",
        )
        should_compile = request.compile
        if should_compile is None:
            should_compile = get_knowledge_settings().auto_compile
        compilation = None
        if should_compile and result["status"] != "already_exists":
            compilation = await compile_source(result["source_id"])
        return ToolResult(
            ok=True,
            data={**result, "compilation": compilation},
            message="文本已加入知识库",
            artifacts=[Artifact(type="knowledge_source", path=str(knowledge_root() / result["path"]))],
        )
    except (ValueError, KnowledgeIngestError, KnowledgeCompileError) as exc:
        return _failure(exc, "KNOWLEDGE_INGEST_FAILED")


async def _ingest_file(payload: dict) -> ToolResult:
    try:
        if not get_knowledge_settings().enabled:
            raise KnowledgeIngestError("知识库已在设置中停用。", "KNOWLEDGE_DISABLED")
        request = FileIngestRequest.model_validate(payload)
        result = ingest_file(request.path, sensitivity=request.sensitivity)
        should_compile = request.compile
        if should_compile is None:
            should_compile = get_knowledge_settings().auto_compile
        compilation = None
        if should_compile and result["status"] != "already_exists":
            compilation = await compile_source(result["source_id"])
        return ToolResult(
            ok=True,
            data={**result, "compilation": compilation},
            message="文件已加入知识库",
            artifacts=[Artifact(type="knowledge_source", path=str(knowledge_root() / result["path"]))],
        )
    except (ValueError, KnowledgeIngestError, KnowledgeCompileError) as exc:
        return _failure(exc, "KNOWLEDGE_INGEST_FAILED")


async def _search(payload: dict) -> ToolResult:
    if not get_knowledge_settings().enabled:
        return _failure(ValueError("知识库已在设置中停用。"), "KNOWLEDGE_DISABLED")
    query = str(payload.get("query") or "").strip()
    if not query:
        return _failure(ValueError("查询内容不能为空。"), "KNOWLEDGE_QUERY_EMPTY")
    results = search_knowledge(query, payload.get("limit"))
    return ToolResult(ok=True, data={"query": query, "results": results}, message=f"找到 {len(results)} 条知识")


async def _answer(payload: dict) -> ToolResult:
    if not get_knowledge_settings().enabled:
        return _failure(ValueError("知识库已在设置中停用。"), "KNOWLEDGE_DISABLED")
    query = str(payload.get("query") or "").strip()
    if not query:
        return _failure(ValueError("查询内容不能为空。"), "KNOWLEDGE_QUERY_EMPTY")
    result = await answer_knowledge(query, payload.get("limit"))
    return ToolResult(ok=True, data=result, message="知识库回答已生成")


async def _compile(payload: dict) -> ToolResult:
    try:
        result = await compile_source(str(payload.get("source_id") or ""))
        return ToolResult(ok=True, data=result, message="知识来源编译完成")
    except KnowledgeCompileError as exc:
        return _failure(exc, "KNOWLEDGE_COMPILE_FAILED")


async def _review(payload: dict) -> ToolResult:
    try:
        result = review_proposal(
            str(payload.get("proposal_id") or ""),
            str(payload.get("decision") or ""),
            force=bool(payload.get("force", False)),
        )
        return ToolResult(ok=True, data=result, message="知识提案已处理")
    except KnowledgeCompileError as exc:
        return _failure(exc, "KNOWLEDGE_REVIEW_FAILED")


async def _lint(_: dict) -> ToolResult:
    report = lint_knowledge()
    return ToolResult(ok=True, data=report, message="知识库检查完成")


async def _semantic_lint(_: dict) -> ToolResult:
    report = await semantic_lint_knowledge()
    return ToolResult(ok=True, data=report, message="知识库语义检查完成")


async def _rebuild(_: dict) -> ToolResult:
    backup = await asyncio.to_thread(backup_database)
    result = await asyncio.to_thread(rebuild_index)
    return ToolResult(
        ok=result["errors"] == 0,
        data={"backup_path": str(backup), **result},
        message="知识库索引已重建",
        artifacts=[Artifact(type="backup", path=str(backup))],
    )


ingest_current_page = ToolDefinition(
    name="knowledge.ingest_current_page",
    description="将用户当前打开的网页保存到本地知识库，并按设置编译为知识条目",
    input_schema={
        "type": "object",
        "properties": {
            "sensitivity": {"type": "string", "enum": ["normal", "private"]},
            "compile": {"type": "boolean"},
        },
        "additionalProperties": False,
    },
    risk_level="low",
    required_permissions=["browser_context:read", "knowledge:write"],
    handler=_ingest_current_page,
)

ingest_text = ToolDefinition(
    name="knowledge.ingest_text",
    description="将用户明确提供的标题和文本保存到本地知识库",
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "content": {"type": "string"},
            "canonical_uri": {"type": ["string", "null"]},
            "sensitivity": {"type": "string", "enum": ["normal", "private"]},
            "compile": {"type": "boolean"},
        },
        "required": ["title", "content"],
        "additionalProperties": False,
    },
    risk_level="low",
    required_permissions=["knowledge:write"],
    handler=_ingest_text,
)

ingest_file_tool = ToolDefinition(
    name="knowledge.ingest_file",
    description="将用户明确指定的本地 Markdown、TXT、PDF、DOCX 或图片文件导入知识库",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "sensitivity": {"type": "string", "enum": ["normal", "private"]},
            "compile": {"type": "boolean"},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    risk_level="low",
    required_permissions=["file:read", "knowledge:write"],
    handler=_ingest_file,
)

search = ToolDefinition(
    name="knowledge.search",
    description="全文搜索本地知识库，返回相关条目和来源",
    input_schema={
        "type": "object",
        "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 30}},
        "required": ["query"],
        "additionalProperties": False,
    },
    risk_level="low",
    required_permissions=["knowledge:read"],
    handler=_search,
)

answer = ToolDefinition(
    name="knowledge.answer",
    description="仅基于本地知识库证据生成带来源的回答",
    input_schema=search.input_schema,
    risk_level="low",
    required_permissions=["knowledge:read"],
    handler=_answer,
)

compile_source_tool = ToolDefinition(
    name="knowledge.compile_source",
    description="将指定来源编译为知识条目或待审提案",
    input_schema={
        "type": "object",
        "properties": {"source_id": {"type": "string"}},
        "required": ["source_id"],
        "additionalProperties": False,
    },
    risk_level="low",
    required_permissions=["knowledge:write"],
    handler=_compile,
)

review = ToolDefinition(
    name="knowledge.review_proposal",
    description="接受或拒绝指定知识更新提案",
    input_schema={
        "type": "object",
        "properties": {
            "proposal_id": {"type": "string"},
            "decision": {"type": "string", "enum": ["accept", "reject"]},
            "force": {"type": "boolean", "description": "基准哈希冲突时明确覆盖当前页面；仅在用户确认后使用"},
        },
        "required": ["proposal_id", "decision"],
        "additionalProperties": False,
    },
    risk_level="medium",
    required_permissions=["knowledge:review"],
    handler=_review,
)

lint = ToolDefinition(
    name="knowledge.lint",
    description="只读检查知识文件、来源、关系和全文索引的一致性",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    risk_level="low",
    required_permissions=["knowledge:read"],
    handler=_lint,
)

semantic_lint = ToolDefinition(
    name="knowledge.semantic_lint",
    description="检查知识矛盾、孤立页面、缺失概念、交叉引用和研究空白",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    risk_level="low",
    required_permissions=["knowledge:read"],
    handler=_semantic_lint,
)

rebuild = ToolDefinition(
    name="knowledge.rebuild_index",
    description="备份数据库后，从 Markdown 重建知识库全文索引",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    risk_level="medium",
    required_permissions=["knowledge:maintain"],
    handler=_rebuild,
)
