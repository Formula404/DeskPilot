from __future__ import annotations

from openpyxl import Workbook

from backend.app.core.paths import data_dir
from backend.app.db.repository import now_iso
from backend.app.schemas.common import Artifact, ToolResult
from backend.app.tools.base import ToolDefinition


async def _handler(payload: dict) -> ToolResult:
    rows = payload.get("rows") or []
    filename = payload.get("filename") or "export"
    path = data_dir() / "exports" / f"{filename}-{now_iso().replace(':', '-')}.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Export"
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    return ToolResult(
        ok=True,
        data={"path": str(path)},
        message="Excel 文件已写入",
        artifacts=[Artifact(type="file", path=str(path))],
    )


write_xlsx = ToolDefinition(
    name="file.write_xlsx",
    description="写入 Excel 文件到 data/exports",
    input_schema={
        "type": "object",
        "properties": {
            "filename": {"type": "string"},
            "rows": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {},
                },
            },
        },
        "required": ["rows"],
        "additionalProperties": False,
    },
    risk_level="low",
    required_permissions=["file:create"],
    handler=_handler,
)
