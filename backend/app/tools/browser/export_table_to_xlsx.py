from __future__ import annotations

import re
from typing import Any

from openpyxl import Workbook

from backend.app.browser.bridge import BrowserBridgeError, browser_bridge
from backend.app.context.runtime_binding import current_browser_target
from backend.app.core.paths import data_dir
from backend.app.db.repository import now_iso
from backend.app.schemas.common import Artifact, ToolError, ToolResult
from backend.app.tools.base import ToolDefinition


def _safe_filename(value: str) -> str:
    normalized = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "-", value).strip(" .-")
    return normalized[:60] or "web-table-export"


def _safe_sheet_title(value: str, fallback: str) -> str:
    normalized = re.sub(r"[\[\]:*?/\\]+", "-", value).strip(" '")
    return (normalized or fallback)[:31]


def _cell_value(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


async def _handler(payload: dict) -> ToolResult:
    filename = _safe_filename(str(payload.get("filename") or "web-table-export"))
    table_index = payload.get("table_index")

    try:
        extracted = await browser_bridge.extract_tables(target=current_browser_target())
    except BrowserBridgeError as exc:
        return ToolResult(
            ok=False,
            message=str(exc),
            error=ToolError(code="BROWSER_BRIDGE_UNAVAILABLE"),
        )

    tables = extracted.get("tables") or []
    if not isinstance(tables, list) or not tables:
        return ToolResult(
            ok=False,
            message="当前网页没有检测到可导出的 HTML 表格。",
            error=ToolError(code="NO_TABLE_FOUND"),
        )

    selected_tables = tables
    if table_index is not None:
        if not isinstance(table_index, int) or table_index < 0 or table_index >= len(tables):
            return ToolResult(
                ok=False,
                message=f"表格序号无效。当前页面共检测到 {len(tables)} 个表格。",
                error=ToolError(code="INVALID_TABLE_INDEX", detail={"table_count": len(tables)}),
            )
        selected_tables = [tables[table_index]]

    path = data_dir() / "exports" / f"{filename}-{now_iso().replace(':', '-')}.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    workbook.remove(workbook.active)
    exported_count = 0
    for index, table in enumerate(selected_tables, start=1):
        rows = table.get("rows") if isinstance(table, dict) else None
        if not isinstance(rows, list) or not rows:
            continue
        title = _safe_sheet_title(str(table.get("caption") or ""), f"Table {index}")
        sheet = workbook.create_sheet(title=title)
        written_rows = 0
        for row in rows:
            if not isinstance(row, list):
                continue
            sheet.append([_cell_value(cell) for cell in row])
            written_rows += 1
        if written_rows > 0:
            exported_count += 1

    if exported_count == 0:
        return ToolResult(
            ok=False,
            message="检测到表格，但没有可写入的行数据。",
            error=ToolError(code="EMPTY_TABLE_ROWS"),
        )

    workbook.save(path)
    return ToolResult(
        ok=True,
        data={
            "path": str(path),
            "table_count": len(tables),
            "exported_table_count": exported_count,
            "url": extracted.get("url"),
            "title": extracted.get("title"),
        },
        message=f"已导出 {exported_count} 个网页表格到 Excel。",
        artifacts=[Artifact(type="file", path=str(path))],
    )


export_table_to_xlsx = ToolDefinition(
    name="browser.export_table_to_xlsx",
    description="抽取当前浏览器页面中的 HTML 表格并保存为 Excel 文件。",
    input_schema={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "导出的 Excel 文件名，不需要包含扩展名。",
            },
            "table_index": {
                "type": "integer",
                "description": "只导出指定序号的表格，0 表示第一个表格；不传则导出全部表格。",
                "minimum": 0,
            },
        },
        "additionalProperties": False,
    },
    output_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "table_count": {"type": "integer"},
            "exported_table_count": {"type": "integer"},
            "url": {"type": ["string", "null"]},
            "title": {"type": ["string", "null"]},
        },
        "additionalProperties": True,
    },
    risk_level="low",
    required_permissions=["browser_context:read", "file:create"],
    handler=_handler,
)
