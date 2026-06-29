from __future__ import annotations

from openai import AsyncOpenAI

from backend.app.core.config import get_settings
from backend.app.schemas.common import ToolError, ToolResult
from backend.app.tools.base import ToolDefinition


async def _handler(payload: dict) -> ToolResult:
    page = payload.get("page") or {}
    instruction = payload.get("instruction") or "总结当前网页"
    text = (page.get("visible_text") or "").strip()
    if not text:
        return ToolResult(
            ok=False,
            message="当前网页没有可总结的可见文本。",
            error=ToolError(code="EMPTY_PAGE_TEXT"),
        )

    settings = get_settings()
    if not settings.openai_api_key:
        summary = _fallback_summary(page, instruction)
        return ToolResult(
            ok=True,
            data={"summary": summary},
            message="未配置 OPENAI_API_KEY，已生成本地占位总结。",
        )

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or "https://api.openai.com/v1",
    )
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": "你是 DeskPilot 的网页总结工具。请用中文简洁总结用户当前网页。",
            },
            {
                "role": "user",
                "content": f"用户指令：{instruction}\n网页标题：{page.get('title')}\nURL：{page.get('url')}\n网页文本：\n{text[:12000]}",
            },
        ],
    )
    return ToolResult(
        ok=True,
        data={"summary": response.choices[0].message.content},
        message="网页总结完成",
    )


def _fallback_summary(page: dict, instruction: str) -> str:
    text = (page.get("visible_text") or "").strip()
    excerpt = text[:1000]
    return (
        f"# {page.get('title') or '网页总结'}\n\n"
        f"当前未配置 OpenAI API Key，因此仅保存网页文本摘录。\n\n"
        f"用户指令：{instruction}\n\n"
        f"URL：{page.get('url')}\n\n"
        f"摘录：\n\n{excerpt}"
    )


summarize_current_page = ToolDefinition(
    name="browser.summarize_current_page",
    description="总结当前网页可见文本",
    input_schema={
        "type": "object",
        "properties": {
            "page": {
                "type": "object",
                "description": "网页上下文数据",
            },
            "instruction": {
                "type": "string",
                "description": "用户的总结要求",
            },
        },
        "required": ["page"],
        "additionalProperties": False,
    },
    risk_level="low",
    required_permissions=["browser_context:read", "openai:call"],
    handler=_handler,
)
