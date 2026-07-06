from __future__ import annotations

import json
import re
from typing import Any

from openai import AsyncOpenAI
from openpyxl import Workbook

from backend.app.browser.bridge import BrowserBridgeError, browser_bridge
from backend.app.core.config import get_settings
from backend.app.core.paths import data_dir
from backend.app.db.repository import now_iso
from backend.app.schemas.common import Artifact, ToolError, ToolResult
from backend.app.tools.base import ToolDefinition


def _safe_filename(value: str) -> str:
    normalized = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "-", value).strip(" .-")
    return normalized[:60] or "web-structured-export"


def _safe_sheet_title(value: str, fallback: str) -> str:
    normalized = re.sub(r"[\[\]:*?/\\]+", "-", value).strip(" '")
    return (normalized or fallback)[:31]


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False) if value else ""


def _extract_json_object(value: str) -> dict[str, Any]:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("model selection must be a JSON object")
    return parsed


def _candidate_summaries(blocks: list[Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for index, block in enumerate(blocks, start=1):
        if not isinstance(block, dict):
            continue
        items = block.get("items") or []
        if not isinstance(items, list):
            continue
        samples: list[dict[str, Any]] = []
        for item in items[:4]:
            if not isinstance(item, dict):
                continue
            samples.append(
                {
                    "title": str(item.get("title") or "")[:180],
                    "description": str(item.get("description") or "")[:360],
                    "first_link_text": str(item.get("first_link_text") or "")[:120],
                    "first_link_url": str(item.get("first_link_url") or "")[:240],
                    "meta": item.get("meta") or [],
                }
            )
        summaries.append(
            {
                "candidate_id": str(block.get("candidate_id") or f"c{index}"),
                "source": block.get("source"),
                "selector_hint": block.get("selector_hint"),
                "item_count": block.get("item_count"),
                "signals": block.get("signals") or {},
                "sample_items": samples,
            }
        )
    return summaries


def _default_fields() -> list[dict[str, str]]:
    return [
        {"name": "标题", "source": "title"},
        {"name": "摘要", "source": "description"},
        {"name": "链接文本", "source": "first_link_text"},
        {"name": "链接", "source": "first_link_url"},
        {"name": "元信息", "source": "meta_json"},
    ]


async def _select_candidate_with_model(
    *,
    instruction: str,
    page_title: str | None,
    page_url: str | None,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        return {"candidate_id": candidates[0]["candidate_id"], "fields": _default_fields(), "reason": "fallback"}

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or "https://api.openai.com/v1",
    )
    response = await client.chat.completions.create(
        model=settings.openai_model,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "你负责从网页 DOM 候选块中选择最符合用户任务的数据块，并给出 Excel 字段映射。"
                    "不要编造候选块中没有的数据。优先选择正文区域、文章/商品/招聘等内容流；"
                    "排除页脚、备案、版权、导航、菜单、广告和纯站点链接。"
                    "只返回 JSON object。字段 source 只能使用："
                    "title, description, first_link_text, first_link_url, meta_json, links_json。"
                    "返回格式：{\"candidate_id\":\"c1\",\"fields\":[{\"name\":\"标题\",\"source\":\"title\"}],\"reason\":\"...\"}"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_instruction": instruction,
                        "page_title": page_title,
                        "page_url": page_url,
                        "candidates": candidates,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    )
    content = response.choices[0].message.content or "{}"
    return _extract_json_object(content)


def _field_value(item: dict[str, Any], source: str) -> Any:
    if source == "title":
        return item.get("title") or ""
    if source == "description":
        return item.get("description") or ""
    if source == "first_link_text":
        return item.get("first_link_text") or ""
    if source == "first_link_url":
        return item.get("first_link_url") or ""
    if source == "meta_json":
        return _json_text(item.get("meta"))
    if source == "links_json":
        return _json_text(item.get("links"))
    return ""


def _normalize_fields(value: Any) -> list[dict[str, str]]:
    allowed_sources = {"title", "description", "first_link_text", "first_link_url", "meta_json", "links_json"}
    fields: list[dict[str, str]] = []
    if isinstance(value, list):
        for field in value[:12]:
            if not isinstance(field, dict):
                continue
            name = str(field.get("name") or "").strip()
            source = str(field.get("source") or "").strip()
            if name and source in allowed_sources:
                fields.append({"name": name[:40], "source": source})
    return fields or _default_fields()


async def _handler(payload: dict) -> ToolResult:
    filename = _safe_filename(str(payload.get("filename") or "web-structured-export"))
    instruction = str(payload.get("instruction") or "导出当前网页中的结构化信息")

    try:
        extracted = await browser_bridge.extract_structured_blocks()
    except BrowserBridgeError as exc:
        return ToolResult(
            ok=False,
            message=str(exc),
            error=ToolError(code="BROWSER_BRIDGE_UNAVAILABLE"),
        )

    blocks = extracted.get("blocks") or []
    if not isinstance(blocks, list) or not blocks:
        return ToolResult(
            ok=False,
            message="当前网页没有检测到可导出的重复列表或卡片结构。",
            error=ToolError(code="NO_STRUCTURED_BLOCK_FOUND"),
        )

    candidate_summaries = _candidate_summaries(blocks)
    if not candidate_summaries:
        return ToolResult(
            ok=False,
            message="当前网页没有可用于模型选择的候选列表或卡片结构。",
            error=ToolError(code="NO_STRUCTURED_CANDIDATE_FOUND"),
        )

    try:
        selection = await _select_candidate_with_model(
            instruction=instruction,
            page_title=str(extracted.get("title") or ""),
            page_url=str(extracted.get("url") or ""),
            candidates=candidate_summaries,
        )
    except Exception as exc:
        return ToolResult(
            ok=False,
            message=f"模型选择候选结构失败：{exc}",
            error=ToolError(code="STRUCTURED_SELECTION_FAILED"),
        )

    selected_candidate_id = str(selection.get("candidate_id") or "")
    selected_block = next(
        (
            block
            for block in blocks
            if isinstance(block, dict) and str(block.get("candidate_id") or "") == selected_candidate_id
        ),
        None,
    )
    if selected_block is None:
        return ToolResult(
            ok=False,
            message=f"模型选择了不存在的候选结构：{selected_candidate_id}",
            error=ToolError(code="INVALID_STRUCTURED_CANDIDATE"),
        )

    fields = _normalize_fields(selection.get("fields"))
    path = data_dir() / "exports" / f"{filename}-{now_iso().replace(':', '-')}.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = _safe_sheet_title("Structured Blocks", "Blocks")
    sheet.append([field["name"] for field in fields] + ["source", "selector_hint"])

    exported_rows = 0
    items = selected_block.get("items") or []
    if not isinstance(items, list):
        items = []
    source = str(selected_block.get("source") or "")
    selector_hint = str(selected_block.get("selector_hint") or "")
    for item in items:
        if not isinstance(item, dict):
            continue
        row = [_field_value(item, field["source"]) for field in fields]
        if not any(str(value).strip() for value in row):
            continue
        sheet.append(row + [source, selector_hint])
        exported_rows += 1

    if exported_rows == 0:
        return ToolResult(
            ok=False,
            message="检测到列表/卡片结构，但没有可写入的条目数据。",
            error=ToolError(code="EMPTY_STRUCTURED_BLOCK_ROWS"),
        )

    workbook.save(path)
    return ToolResult(
        ok=True,
        data={
            "path": str(path),
            "block_count": len(blocks),
            "selected_candidate_id": selected_candidate_id,
            "selection_reason": selection.get("reason"),
            "exported_row_count": exported_rows,
            "url": extracted.get("url"),
            "title": extracted.get("title"),
        },
        message=f"已导出 {exported_rows} 条列表/卡片数据到 Excel。",
        artifacts=[Artifact(type="file", path=str(path))],
    )


export_structured_blocks_to_xlsx = ToolDefinition(
    name="browser.export_structured_blocks_to_xlsx",
    description="抽取当前浏览器页面中的重复列表或卡片结构，并保存为 Excel 文件。",
    input_schema={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "导出的 Excel 文件名，不需要包含扩展名。",
            },
            "instruction": {
                "type": "string",
                "description": "用户希望从网页中抽取的数据类型，例如博客信息、招聘信息、商品信息。",
            },
        },
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "block_count": {"type": "integer"},
            "exported_row_count": {"type": "integer"},
            "url": {"type": ["string", "null"]},
            "title": {"type": ["string", "null"]},
        },
        "additionalProperties": True,
    },
    risk_level="low",
    required_permissions=["browser_context:read", "file:create"],
    handler=_handler,
)
