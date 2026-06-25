from __future__ import annotations

from backend.app.tools.registry import tool_registry


def test_default_tools_registered() -> None:
    names = {tool.name for tool in tool_registry.list()}
    assert "browser.get_current_page" in names
    assert "browser.summarize_current_page" in names
    assert "file.write_markdown" in names
    assert "file.write_xlsx" in names
