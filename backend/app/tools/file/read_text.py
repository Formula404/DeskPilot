from __future__ import annotations

from backend.app.artifacts.service import resolve_artifact_file
from backend.app.schemas.common import ToolError, ToolResult
from backend.app.tools.base import ToolDefinition


async def _handler(payload: dict) -> ToolResult:
    try:
        path = resolve_artifact_file(str(payload.get("path") or ""))
    except ValueError as exc:
        return ToolResult(ok=False, message=str(exc), error=ToolError(code="FILE_PATH_NOT_ALLOWED"))
    if path.suffix.lower() not in {".md", ".txt", ".json", ".csv", ".tsv"}:
        return ToolResult(
            ok=False,
            message="当前只支持读取 Markdown、TXT、JSON、CSV 和 TSV 文本制品。",
            error=ToolError(code="FILE_FORMAT_UNSUPPORTED"),
        )
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return ToolResult(ok=False, message=str(exc), error=ToolError(code="FILE_READ_FAILED"))
    return ToolResult(
        ok=True,
        data={"path": str(path), "content": content[:50000], "truncated": len(content) > 50000},
        message="文本制品已读取",
    )


read_text = ToolDefinition(
    name="file.read_text",
    domain="file",
    description="读取 DeskPilot 允许目录内的 Markdown、TXT、JSON、CSV 或 TSV 文本制品",
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string", "minLength": 1}},
        "required": ["path"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
            "truncated": {"type": "boolean"},
        },
        "required": ["path", "content", "truncated"],
        "additionalProperties": False,
    },
    risk_level="low",
    required_permissions=["file:read"],
    preconditions=["path_within_allowed_artifact_roots"],
    side_effects=[],
    handler=_handler,
)
