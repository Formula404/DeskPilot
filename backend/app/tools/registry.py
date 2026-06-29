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

    def list(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    async def call(self, name: str, payload: dict) -> ToolResult:
        tool = self.get(name)
        return await tool.handler(payload)


tool_registry = ToolRegistry()


def register_default_tools() -> None:
    from backend.app.tools.browser.collect_current_page import collect_current_page
    from backend.app.tools.browser.current_page import get_current_page
    from backend.app.tools.browser.summarize import summarize_current_page
    from backend.app.tools.file.write_markdown import write_markdown
    from backend.app.tools.file.write_xlsx import write_xlsx

    for tool in [
        collect_current_page,
        get_current_page,
        summarize_current_page,
        write_markdown,
        write_xlsx,
    ]:
        tool_registry.register(tool)


register_default_tools()
