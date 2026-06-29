from __future__ import annotations

from backend.app.db.repository import get_latest_browser_context
from backend.app.schemas.common import ToolError, ToolResult
from backend.app.tools.base import ToolDefinition


async def _handler(_: dict) -> ToolResult:
    context = get_latest_browser_context()
    if not context:
        return ToolResult(
            ok=False,
            message="未获取到当前网页上下文，请先安装并启用浏览器扩展。",
            error=ToolError(code="BROWSER_CONTEXT_NOT_FOUND"),
        )
    return ToolResult(ok=True, data=context, message="已获取当前网页上下文")


get_current_page = ToolDefinition(
    name="browser.get_current_page",
    description="获取浏览器扩展最近上报的当前网页上下文",
    input_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    risk_level="low",
    required_permissions=["browser_context:read"],
    handler=_handler,
)
