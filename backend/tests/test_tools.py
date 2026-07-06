from __future__ import annotations

import pytest

from backend.app.agent import nodes
from backend.app.agent.intents import detect_intent
from backend.app.agent.tool_calling import ToolCallingError
from backend.app.browser.bridge import BrowserBridge, BrowserBridgeError
from backend.app.tools.registry import tool_registry


def test_default_tools_registered() -> None:
    names = {tool.name for tool in tool_registry.list()}
    assert "browser.collect_current_page" in names
    assert "browser.get_current_page" in names
    assert "browser.summarize_current_page" in names
    assert "browser.export_table_to_xlsx" in names
    assert "browser.export_structured_blocks_to_xlsx" in names
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


def test_web_table_export_allowed_tools_have_schemas() -> None:
    tools = tool_registry.openai_tools(
        [
            "browser.export_table_to_xlsx",
            "browser.export_structured_blocks_to_xlsx",
        ]
    )
    names = {tool["function"]["name"] for tool in tools}
    assert names == {
        "browser_export_table_to_xlsx",
        "browser_export_structured_blocks_to_xlsx",
    }


def test_table_export_intent_takes_priority_over_page_keywords() -> None:
    assert detect_intent("把当前网页里的表格导出成 Excel") == "web_table_export"


@pytest.mark.asyncio
async def test_write_markdown_rejects_empty_content() -> None:
    result = await tool_registry.call("file.write_markdown", {"title": "empty", "content": ""})
    assert not result.ok
    assert result.error
    assert result.error.code == "EMPTY_MARKDOWN_CONTENT"


def test_table_summary_intent_prefers_summary() -> None:
    assert detect_intent("总结这个表格页面") == "web_page_summary"


@pytest.mark.asyncio
async def test_export_current_page_table_returns_error_on_tool_calling_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_web_table_export_tool_agent(*, task_id: str, user_input: str) -> dict:
        raise ToolCallingError("boom")

    monkeypatch.setattr(nodes, "run_web_table_export_tool_agent", fake_run_web_table_export_tool_agent)
    result = await nodes.export_current_page_table({"task_id": "task-1", "user_input": "导出表格"})

    assert result["error"] == "boom"


@pytest.mark.asyncio
async def test_extract_tables_rejects_non_dict_data(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = BrowserBridge()

    async def fake_command(*args, **kwargs) -> dict:
        return {"ok": True, "data": ["bad"]}

    monkeypatch.setattr(bridge, "command", fake_command)
    with pytest.raises(BrowserBridgeError, match="无效的表格数据"):
        await bridge.extract_tables()
