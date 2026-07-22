from __future__ import annotations

from backend.app.context.runtime_binding import current_browser_target
from backend.app.db.repository import get_browser_context
from backend.app.schemas.common import ToolError, ToolResult
from backend.app.tools.base import ToolDefinition


async def _handler(_: dict) -> ToolResult:
    target = current_browser_target() or {}
    context_id = target.get("browser_context_id")
    context = get_browser_context(str(context_id)) if context_id else None
    if not context:
        return ToolResult(
            ok=False,
            message="任务没有绑定可读取的网页上下文，不能使用全局最新页面代替。",
            error=ToolError(code="BOUND_BROWSER_CONTEXT_NOT_FOUND"),
        )
    return ToolResult(ok=True, data=context, message="已获取当前网页上下文")


get_current_page = ToolDefinition(
    name="browser.get_current_page",
    description="按当前任务绑定的上下文 ID 获取网页上下文",
    input_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    risk_level="low",
    required_permissions=["browser_context:read"],
    handler=_handler,
)
