from __future__ import annotations

from backend.app.browser.bridge import BrowserBridgeError, browser_bridge
from backend.app.db.repository import now_iso, save_browser_context
from backend.app.schemas.common import ToolError, ToolResult
from backend.app.tools.base import ToolDefinition


async def _handler(_: dict) -> ToolResult:
    try:
        page = await browser_bridge.collect_page()
    except BrowserBridgeError as exc:
        return ToolResult(
            ok=False,
            message=str(exc),
            error=ToolError(code="BROWSER_BRIDGE_UNAVAILABLE"),
        )

    url = page.get("url")
    if not isinstance(url, str) or not url:
        return ToolResult(
            ok=False,
            message="浏览器扩展未返回有效 URL。",
            error=ToolError(code="INVALID_BROWSER_CONTEXT"),
        )

    context_id = save_browser_context(
        tab_id=str(page.get("tab_id")) if page.get("tab_id") is not None else None,
        url=url,
        title=page.get("title"),
        visible_text=page.get("visible_text") or "",
        dom_summary=page.get("dom_summary") or [],
        captured_at=page.get("captured_at") or now_iso(),
    )
    data = {**page, "id": context_id, "context_id": context_id}
    return ToolResult(ok=True, data=data, message="已通过浏览器扩展采集当前网页上下文")


collect_current_page = ToolDefinition(
    name="browser.collect_current_page",
    description="通过浏览器扩展通道实时采集当前网页上下文",
    input_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "title": {"type": ["string", "null"]},
            "visible_text": {"type": "string"},
            "dom_summary": {"type": "array"},
            "context_id": {"type": "string"},
        },
        "additionalProperties": True,
    },
    risk_level="low",
    required_permissions=["browser_context:read"],
    handler=_handler,
)
