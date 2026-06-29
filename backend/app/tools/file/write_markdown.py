from __future__ import annotations

import re

from backend.app.core.paths import data_dir
from backend.app.db.repository import now_iso
from backend.app.schemas.common import Artifact, ToolError, ToolResult
from backend.app.tools.base import ToolDefinition


async def _handler(payload: dict) -> ToolResult:
    title = (payload.get("title") or "").strip() or "summary"
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        return ToolResult(
            ok=False,
            message="Markdown 内容不能为空。",
            error=ToolError(code="EMPTY_MARKDOWN_CONTENT"),
        )
    filename = _slugify(title) or "summary"
    path = data_dir() / "exports" / f"{filename}-{now_iso().replace(':', '-')}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return ToolResult(
        ok=True,
        data={"path": str(path)},
        message="Markdown 文件已写入",
        artifacts=[Artifact(type="file", path=str(path))],
    )


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value, flags=re.UNICODE)
    return normalized.strip("-")[:60]


write_markdown = ToolDefinition(
    name="file.write_markdown",
    description="写入 Markdown 文件到 data/exports",
    input_schema={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "用于生成文件名的标题",
            },
            "content": {
                "type": "string",
                "description": "要写入 Markdown 文件的完整内容",
            },
        },
        "required": ["title", "content"],
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
        },
        "required": ["path"],
        "additionalProperties": True,
    },
    risk_level="low",
    required_permissions=["file:create"],
    handler=_handler,
)
