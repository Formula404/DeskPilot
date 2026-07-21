from __future__ import annotations

from backend.app.schemas.common import ToolResult
from backend.app.tools.base import ToolDefinition


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

    def list(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def openai_tools(self, allowed_names: list[str]) -> list[dict]:
        return [self.get(name).to_openai_tool() for name in allowed_names]

    async def call(self, name: str, payload: dict) -> ToolResult:
        tool = self.get(name)
        return await tool.handler(payload)


tool_registry = ToolRegistry()


def register_default_tools() -> None:
    from backend.app.tools.browser.collect_current_page import collect_current_page
    from backend.app.tools.browser.current_page import get_current_page
    from backend.app.tools.browser.export_structured_blocks_to_xlsx import export_structured_blocks_to_xlsx
    from backend.app.tools.browser.export_table_to_xlsx import export_table_to_xlsx
    from backend.app.tools.browser.summarize import summarize_current_page
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
