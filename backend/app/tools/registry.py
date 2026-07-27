from __future__ import annotations

import asyncio
from typing import Any

from backend.app.schemas.common import ToolError, ToolResult
from backend.app.tools.base import ToolDefinition


class SchemaValidationError(ValueError):
    pass


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def validate_json_schema(value: Any, schema: dict[str, Any], *, path: str = "$") -> None:
    expected = schema.get("type")
    expected_types = expected if isinstance(expected, list) else [expected] if expected else []
    if expected_types and not any(_matches_type(value, item) for item in expected_types):
        raise SchemaValidationError(f"{path} 类型不符合 Schema，期望 {expected_types}。")
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaValidationError(f"{path} 不在允许值 {schema['enum']} 中。")
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            raise SchemaValidationError(f"{path} 长度小于下限。")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise SchemaValidationError(f"{path} 长度超过上限。")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaValidationError(f"{path} 小于最小值。")
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaValidationError(f"{path} 大于最大值。")
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        missing = [name for name in schema.get("required") or [] if name not in value]
        if missing:
            raise SchemaValidationError(f"{path} 缺少必填字段：{missing}")
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value) - set(properties))
            if extras:
                raise SchemaValidationError(f"{path} 包含未声明字段：{extras}")
        for name, child in value.items():
            child_schema = properties.get(name)
            if isinstance(child_schema, dict):
                validate_json_schema(child, child_schema, path=f"{path}.{name}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, child in enumerate(value):
            validate_json_schema(child, schema["items"], path=f"{path}[{index}]")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        return self._tools[name]

    def get_by_openai_name(self, openai_name: str) -> ToolDefinition:
        for tool in self._tools.values():
            if tool.openai_name == openai_name:
                return tool
        raise KeyError(openai_name)

    def list(self, *, domain: str | None = None, caller: str | None = None) -> list[ToolDefinition]:
        tools = list(self._tools.values())
        if domain is not None:
            tools = [tool for tool in tools if tool.domain == domain]
        if caller is not None:
            tools = [tool for tool in tools if caller in tool.allowed_callers]
        return tools

    def openai_tools(self, allowed_names: list[str], *, caller: str | None = None) -> list[dict]:
        result = []
        for name in allowed_names:
            tool = self.get(name)
            if caller is not None and caller not in tool.allowed_callers:
                raise PermissionError(f"调用者 {caller} 不允许发现工具 {name}。")
            result.append(tool.to_openai_tool())
        return result

    async def call(
        self,
        name: str,
        payload: dict,
        *,
        caller: str = "system",
        confirmed: bool = False,
    ) -> ToolResult:
        try:
            tool = self.get(name)
        except KeyError:
            return ToolResult(
                ok=False,
                message=f"工具不存在：{name}",
                error=ToolError(code="TOOL_NOT_FOUND", detail={"tool": name}),
            )
        if caller not in tool.allowed_callers:
            return ToolResult(
                ok=False,
                message=f"调用者 {caller} 无权调用工具 {name}。",
                error=ToolError(code="TOOL_CALLER_FORBIDDEN", detail={"caller": caller}),
            )
        if caller.endswith("_agent") and "browser_context:read" in tool.required_permissions:
            from backend.app.context.runtime_binding import current_browser_target

            if not current_browser_target():
                return ToolResult(
                    ok=False,
                    message="Agent 网页工具缺少任务绑定的浏览器目标，不能使用执行时的全局当前页代替。",
                    error=ToolError(code="BOUND_BROWSER_TARGET_REQUIRED", detail={"tool": name}),
                )
        try:
            validate_json_schema(payload, tool.input_schema)
        except SchemaValidationError as exc:
            return ToolResult(
                ok=False,
                message=str(exc),
                error=ToolError(code="TOOL_ARGUMENT_INVALID", detail={"tool": name}),
            )
        if tool.requires_confirmation and not confirmed:
            return ToolResult(
                ok=False,
                message=f"工具 {name} 需要用户明确确认，当前未执行。",
                error=ToolError(
                    code="APPROVAL_REQUIRED",
                    detail={"tool": name, "risk_level": tool.risk_level},
                ),
            )
        try:
            result = await asyncio.wait_for(tool.handler(payload), timeout=tool.timeout_seconds)
        except TimeoutError:
            return ToolResult(
                ok=False,
                message=f"工具 {name} 执行超时。",
                error=ToolError(code="TOOL_TIMEOUT", detail={"timeout_seconds": tool.timeout_seconds}),
            )
        except Exception as exc:
            return ToolResult(
                ok=False,
                message=f"工具 {name} 执行失败：{exc}",
                error=ToolError(code="TOOL_EXECUTION_FAILED", detail={"type": type(exc).__name__}),
            )
        if result.ok:
            try:
                validate_json_schema(result.data or {}, tool.output_schema)
            except SchemaValidationError as exc:
                return ToolResult(
                    ok=False,
                    message=f"工具 {name} 返回值不符合 Schema：{exc}",
                    error=ToolError(code="TOOL_OUTPUT_INVALID", detail={"tool": name}),
                )
        return result


tool_registry = ToolRegistry()


def register_default_tools() -> None:
    from backend.app.tools.browser.collect_current_page import collect_current_page
    from backend.app.tools.browser.current_page import get_current_page
    from backend.app.tools.browser.export_structured_blocks_to_xlsx import export_structured_blocks_to_xlsx
    from backend.app.tools.browser.export_table_to_xlsx import export_table_to_xlsx
    from backend.app.tools.browser.summarize import summarize_current_page
    from backend.app.tools.file.read_text import read_text
    from backend.app.tools.file.write_markdown import write_markdown
    from backend.app.tools.file.write_xlsx import write_xlsx
    from backend.app.tools.knowledge.operations import (
        answer,
        compile_source_tool,
        ingest_current_page,
        ingest_file_tool,
        ingest_text,
        lint,
        semantic_lint,
        rebuild,
        review,
        search,
    )

    for tool in [
        collect_current_page,
        get_current_page,
        export_structured_blocks_to_xlsx,
        export_table_to_xlsx,
        summarize_current_page,
        read_text,
        write_markdown,
        write_xlsx,
        ingest_current_page,
        ingest_file_tool,
        ingest_text,
        search,
        answer,
        compile_source_tool,
        review,
        lint,
        semantic_lint,
        rebuild,
    ]:
        tool_registry.register(tool)


register_default_tools()
