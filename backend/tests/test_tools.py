from __future__ import annotations

import pytest

from backend.app.tools.registry import tool_registry


def test_default_tools_registered() -> None:
    names = {tool.name for tool in tool_registry.list()}
    assert "browser.collect_current_page" in names
    assert "browser.get_current_page" in names
    assert "browser.summarize_current_page" in names
    assert "file.write_markdown" in names
    assert "file.write_xlsx" in names


def test_openai_tool_mapping() -> None:
    tool = tool_registry.get("browser.collect_current_page")
    assert tool.openai_name == "browser_collect_current_page"
    assert tool_registry.get_by_openai_name("browser_collect_current_page").name == tool.name
    openai_tool = tool.to_openai_tool()
    assert openai_tool["type"] == "function"
    assert openai_tool["function"]["parameters"]["type"] == "object"


def test_web_page_summary_allowed_tools_have_schemas() -> None:
    tools = tool_registry.openai_tools(["browser.collect_current_page", "file.write_markdown"])
    names = {tool["function"]["name"] for tool in tools}
    assert names == {"browser_collect_current_page", "file_write_markdown"}


@pytest.mark.asyncio
async def test_write_markdown_rejects_empty_content() -> None:
    result = await tool_registry.call("file.write_markdown", {"title": "empty", "content": ""})
    assert not result.ok
    assert result.error
    assert result.error.code == "EMPTY_MARKDOWN_CONTENT"
