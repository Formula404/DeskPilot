from __future__ import annotations

from typing import Any

from backend.app.agent.specialists.base import SpecialistAgent, SpecialistExecutionContext
from backend.app.agent.specialists.models import FileAgentRequest, SpecialistAgentResult, StrictRequest


def _find_value(value: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        for key in keys:
            if key in value and value[key] not in (None, "", [], {}):
                return value[key]
        for child in value.values():
            found = _find_value(child, keys)
            if found not in (None, "", [], {}):
                return found
    if isinstance(value, list):
        for child in value:
            found = _find_value(child, keys)
            if found not in (None, "", [], {}):
                return found
    return None


class FileAgent(SpecialistAgent):
    name = "file"
    prompt_version = "file-agent-prompt-v1"
    request_model = FileAgentRequest
    allowed_tools = ("file.read_text", "file.write_markdown", "file.write_xlsx")
    system_prompt = (
        "你是 DeskPilot 的 File Agent。只在允许目录内读写制品，只调用 File 白名单工具。"
        "优先使用 Manager 提供的依赖结果内容，禁止猜测缺失内容或路径；创建新文件时不覆盖原文件。"
        "不要调用其他专业 Agent。"
    )

    async def run_fallback(
        self, request: StrictRequest, context: SpecialistExecutionContext
    ) -> SpecialistAgentResult:
        objective = request.objective.lower()
        target_format = getattr(request, "target_format", None)
        wants_xlsx = target_format in {"xlsx", "excel"} or any(word in objective for word in ("excel", "xlsx"))
        if wants_xlsx:
            rows = _find_value(context.dependency_results, ("rows", "table", "data_rows"))
            if not isinstance(rows, list):
                return SpecialistAgentResult(
                    status="needs_input",
                    summary="依赖结果中没有可写入 Excel 的结构化行数据。",
                    missing_inputs=["二维 rows 数据"],
                )
            arguments = {"rows": rows, "filename": getattr(request, "preferred_filename", None) or "export"}
            tool = "file.write_xlsx"
        else:
            content = _find_value(context.dependency_results, ("summary", "answer", "content", "visible_text"))
            if not isinstance(content, str) or not content.strip():
                return SpecialistAgentResult(
                    status="needs_input",
                    summary="依赖结果中没有可写入 Markdown 的文本内容。",
                    missing_inputs=["文本来源"],
                )
            arguments = {
                "title": getattr(request, "preferred_filename", None) or "DeskPilot 导出",
                "content": content,
            }
            tool = "file.write_markdown"
        result, observation, _ = await self.execute_fallback_tool(tool, arguments, request, context)
        return SpecialistAgentResult(
            status="completed" if result.ok else "failed",
            summary=result.message,
            artifacts=[item.model_dump() for item in result.artifacts],
            observations=[observation],
        )

