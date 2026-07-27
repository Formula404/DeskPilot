from __future__ import annotations

from datetime import UTC, datetime, timedelta
import asyncio
from types import SimpleNamespace

import pytest

from backend.app.browser.bridge import BrowserBridge, BrowserBridgeError
from backend.app.context.budget import ContextBudgeter
from backend.app.context import service as context_service
from backend.app.context.service import ContextBuilder, browser_target
from backend.app.agent.intents import detect_intent
from backend.app.agent import nodes
from backend.app.agent.nodes import propose_or_write_memory
from backend.app.agent.tool_calling import _arguments_for_error, _compact_text
from backend.app.core.config import get_settings
from backend.app.db.connection import init_db
from backend.app.db.connection import connect
from backend.app.db.repository import (
    add_message,
    add_task_step,
    create_session,
    create_task,
    delete_session,
    get_context_snapshot,
    get_task,
    save_context_snapshot,
)
from backend.app.core.task_lifecycle import cancel_background_tasks
from backend.app.memory.repository import save_memory


@pytest.fixture
def context_data_dir(tmp_path):
    settings = get_settings()
    original = settings.data_dir
    settings.data_dir = tmp_path / "data"
    init_db()
    try:
        yield settings.data_dir
    finally:
        settings.data_dir = original


def _snapshot(session_id: str, *, tab_id: str, url: str, expired: bool = False) -> str:
    now = datetime.now(UTC)
    return save_context_snapshot(
        session_id=session_id,
        source="test",
        window={"title": f"window-{tab_id}"},
        browser={"tab_id": tab_id, "url": url, "title": f"page-{tab_id}"},
        selection={},
        attachments=[],
        sensitivity="normal",
        captured_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=-1 if expired else 10)).isoformat(),
    )


def test_task_persists_session_turn_and_snapshot_binding(context_data_dir) -> None:
    session_id = create_session()
    snapshot_id = _snapshot(session_id, tab_id="12", url="https://example.com/a")
    turn_id = add_message(session_id, role="user", content="总结这个页面")
    task_id = create_task(
        "总结这个页面",
        session_id=session_id,
        turn_id=turn_id,
        context_snapshot_id=snapshot_id,
    )

    task = get_task(task_id)
    assert task is not None
    assert task["session_id"] == session_id
    assert task["turn_id"] == turn_id
    assert task["context_snapshot_id"] == snapshot_id
    assert get_context_snapshot(snapshot_id)["browser"]["tab_id"] == "12"


@pytest.mark.asyncio
async def test_collect_metadata_falls_back_for_legacy_extension(monkeypatch) -> None:
    bridge = BrowserBridge()
    commands = []

    async def fake_command(command: str, **kwargs) -> dict:
        commands.append((command, kwargs))
        if command == "collect_metadata":
            return {
                "ok": False,
                "error": {
                    "code": "UNSUPPORTED_COMMAND",
                    "message": "不支持的浏览器命令：collect_metadata",
                },
            }
        return {
            "ok": True,
            "data": {
                "tab_id": 17,
                "url": "https://example.com/legacy",
                "title": "Legacy page",
                "visible_text": "not persisted by the snapshot service",
            },
        }

    monkeypatch.setattr(bridge, "command", fake_command)

    metadata = await bridge.collect_metadata()

    assert [item[0] for item in commands] == ["collect_metadata", "collect_page"]
    assert commands[1][1]["payload"]["include_visible_text"] is False
    assert metadata["tab_id"] == 17
    assert metadata["url"] == "https://example.com/legacy"
    assert metadata["document_id"] == "17:https://example.com/legacy"
    assert len(metadata["content_hash"]) == 64
    assert "legacy_collect_page_fallback" in metadata["_degraded_reasons"]
    assert "content_hash_derived_from_legacy_page" in metadata["_degraded_reasons"]


@pytest.mark.asyncio
async def test_context_builder_keeps_concurrent_task_targets_isolated(context_data_dir) -> None:
    session_id = create_session()
    snapshot_a = _snapshot(session_id, tab_id="1", url="https://example.com/a")
    snapshot_b = _snapshot(session_id, tab_id="2", url="https://example.com/b")
    task_a = create_task("总结页面 A", session_id=session_id, context_snapshot_id=snapshot_a)
    task_b = create_task("总结页面 B", session_id=session_id, context_snapshot_id=snapshot_b)

    builder = ContextBuilder()
    bundle_a = await builder.build(task_id=task_a, intent="web_page_summary")
    bundle_b = await builder.build(task_id=task_b, intent="web_page_summary")

    assert browser_target(bundle_a["snapshot"])["tab"] == 1
    assert browser_target(bundle_b["snapshot"])["tab"] == 2
    assert bundle_a["snapshot"]["browser"]["url"] == "https://example.com/a"
    assert bundle_b["snapshot"]["browser"]["url"] == "https://example.com/b"


@pytest.mark.asyncio
async def test_manager_snapshot_metadata_is_required_under_tight_budget(context_data_dir) -> None:
    session_id = create_session()
    snapshot_id = _snapshot(session_id, tab_id="21", url="https://example.com/required")
    task_id = create_task(
        "当前这个页面是什么？",
        session_id=session_id,
        context_snapshot_id=snapshot_id,
    )
    bundle = await ContextBuilder().build(task_id=task_id, agent="manager", token_budget=1)
    kinds = {item["kind"] for item in bundle["blocks"]}
    assert {"user_message", "foreground_window", "browser_page_metadata"} <= kinds
    assert all(
        item.get("required")
        for item in bundle["blocks"]
        if item["kind"] in {"user_message", "foreground_window", "browser_page_metadata"}
    )


@pytest.mark.asyncio
async def test_knowledge_agent_gets_own_rag_context_but_manager_does_not(
    context_data_dir, monkeypatch
) -> None:
    task_id = create_task("从知识库查一下 X")
    monkeypatch.setattr(
        context_service,
        "get_knowledge_settings",
        lambda: SimpleNamespace(enabled=True, allow_private_remote=False),
    )
    monkeypatch.setattr(
        context_service,
        "search_knowledge",
        lambda query, limit: [
            {
                "id": "note-x",
                "title": "X",
                "summary": "X 的可靠摘要",
                "overview": "",
                "path": "notes/x.md",
                "status": "active",
                "updated_at": datetime.now(UTC).isoformat(),
                "sources": [
                    {
                        "source_id": "source-x",
                        "snapshot_id": "snapshot-x",
                        "source_title": "X source",
                        "canonical_uri": "https://example.com/x",
                        "sensitivity": "normal",
                    }
                ],
            },
            {
                "id": "note-private",
                "title": "Private",
                "summary": "不应发送给远程模型",
                "overview": "",
                "path": "notes/private.md",
                "status": "active",
                "sensitivity": "private",
                "updated_at": datetime.now(UTC).isoformat(),
                "sources": [],
            },
        ],
    )

    manager_bundle = await ContextBuilder().build(task_id=task_id, agent="manager")
    knowledge_bundle = await ContextBuilder().build(task_id=task_id, agent="knowledge")

    assert manager_bundle["knowledge"] == []
    assert not any(item["kind"] == "knowledge_evidence" for item in manager_bundle["blocks"])
    assert knowledge_bundle["execution"]["context_policy_key"] == "agent:knowledge"
    assert len(knowledge_bundle["knowledge"]) == 1
    assert knowledge_bundle["knowledge"][0]["content"]["note_id"] == "note-x"
    assert knowledge_bundle["knowledge"][0]["trust"] == "untrusted"


@pytest.mark.asyncio
async def test_builder_resolves_pronoun_to_recent_artifact(context_data_dir) -> None:
    session_id = create_session()
    first_task = create_task("导出表格", session_id=session_id)
    add_task_step(
        first_task,
        step_index=1,
        step_type="tool",
        name="file_write_xlsx",
        status="completed",
        output_data={"artifacts": [{"type": "file", "path": "D:/exports/sales.xlsx"}]},
    )
    task_id = create_task("把它改成中文文件名", session_id=session_id)

    bundle = await ContextBuilder().build(task_id=task_id, intent="general_chat")
    references = bundle["execution"]["resolved_references"]
    assert references["它"]["type"] == "artifact"
    assert references["它"]["path"].endswith("sales.xlsx")


def test_budgeter_never_evicts_required_block_and_selects_relevant_first() -> None:
    budgeter = ContextBudgeter()
    blocks = [
        {
            "id": "instruction",
            "kind": "user_message",
            "content": "当前指令",
            "required": True,
            "relevance_score": 1.0,
            "token_estimate": 10,
        },
        {
            "id": "low",
            "kind": "memory",
            "content": "x" * 600,
            "relevance_score": 0.1,
            "token_estimate": 200,
        },
        {
            "id": "high",
            "kind": "knowledge_evidence",
            "content": "关键证据",
            "relevance_score": 0.99,
            "token_estimate": 10,
        },
    ]
    selected, audit = budgeter.select(blocks, max_tokens=40)
    assert [block["id"] for block in selected] == ["instruction", "high"]
    assert audit["dropped_or_truncated_blocks"] == 1


def test_secret_memory_is_rejected(context_data_dir) -> None:
    with pytest.raises(ValueError, match="Secret"):
        save_memory(kind="fact", content="api_key=sk-abcdefghijklmnop")


def test_task_step_audit_redacts_secrets(context_data_dir) -> None:
    task_id = create_task("test")
    add_task_step(
        task_id,
        step_index=1,
        step_type="tool",
        name="test_tool",
        status="completed",
        input_data={"api_key": "sk-abcdefghijklmnop"},
    )
    with connect() as connection:
        row = connection.execute(
            "SELECT input_json FROM task_steps WHERE task_id = ?", (task_id,)
        ).fetchone()
    assert "sk-abcdefghijklmnop" not in row["input_json"]
    assert "REDACTED_SECRET" in row["input_json"]


@pytest.mark.asyncio
async def test_explicit_memory_write_does_not_require_chat_model(context_data_dir) -> None:
    session_id = create_session()
    task_id = create_task("记住我默认使用中文", session_id=session_id)
    assert detect_intent("记住我默认使用中文") == "memory_write"
    state = await propose_or_write_memory(
        {"task_id": task_id, "session_id": session_id, "user_input": "记住我默认使用中文"}
    )
    assert state["step_count"] == 1
    with connect() as connection:
        row = connection.execute("SELECT kind, content FROM memory_items").fetchone()
    assert row["kind"] == "preference"
    assert row["content"] == "我默认使用中文"


def test_deleting_session_removes_bound_task_audit(context_data_dir) -> None:
    session_id = create_session()
    message_id = add_message(session_id, role="user", content="temporary")
    snapshot_id = _snapshot(session_id, tab_id="3", url="https://example.com/temp")
    task_id = create_task("temporary", session_id=session_id)
    add_task_step(task_id, step_index=1, step_type="agent", name="test", status="completed")
    assert delete_session(session_id)
    with connect() as connection:
        assert connection.execute("SELECT 1 FROM task_runs WHERE id = ?", (task_id,)).fetchone() is None
        assert connection.execute("SELECT 1 FROM task_steps WHERE task_id = ?", (task_id,)).fetchone() is None
        assert connection.execute("SELECT 1 FROM messages WHERE id = ?", (message_id,)).fetchone() is None
        assert connection.execute("SELECT 1 FROM context_snapshots WHERE id = ?", (snapshot_id,)).fetchone() is None


@pytest.mark.asyncio
async def test_general_chat_publishes_running_and_completed_steps(context_data_dir, monkeypatch) -> None:
    task_id = create_task("hello")
    published = []

    async def create_completion(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="hi"))]
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create_completion))
    )
    settings = SimpleNamespace(
        openai_api_key="configured",
        openai_base_url="https://example.com/v1",
        openai_model="test-model",
        request_timeout_seconds=10,
        temperature=0.2,
        general=SimpleNamespace(response_language="en"),
    )
    monkeypatch.setattr(nodes, "get_settings", lambda: settings)
    monkeypatch.setattr(nodes, "AsyncOpenAI", lambda **kwargs: client)

    async def publish(step):
        published.append(step)

    result = await nodes.general_chat(
        {"task_id": task_id, "user_input": "hello", "publish_step": publish}
    )
    assert result["final_response"] == "hi"
    assert [step["status"] for step in published] == ["running", "completed"]
    with connect() as connection:
        row = connection.execute(
            "SELECT status FROM task_steps WHERE task_id = ? AND name = 'general_chat_completion'",
            (task_id,),
        ).fetchone()
    assert row["status"] == "completed"


def test_compaction_preserves_dotted_tokens_and_enforces_single_paragraph_limit() -> None:
    text = ("Dr. Smith rated it 3.5 stars; see https://example.com/page. " * 20).strip()
    compacted, truncated = _compact_text(text, "Smith", max_chars=120)
    payload = compacted.removesuffix("\n\n[内容已按任务相关性压缩]")
    assert truncated
    assert len(payload) <= 120
    assert "Dr. Smith" in payload
    assert "3.5" in payload
    assert "https://example.com/page" in payload


def test_tool_failure_keeps_parsed_arguments() -> None:
    parsed = {"url": "https://example.com", "limit": 5}
    assert _arguments_for_error(parsed, '{"url":"ignored"}') == parsed
    assert _arguments_for_error(None, "not-json") == {"raw_arguments": "not-json"}


@pytest.mark.asyncio
async def test_recovered_tasks_are_cancelled_without_blocking_shutdown() -> None:
    cancelled = asyncio.Event()

    async def long_running():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    task = asyncio.create_task(long_running())
    await asyncio.sleep(0)
    await asyncio.wait_for(cancel_background_tasks([task]), timeout=0.2)
    assert task.cancelled()
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_browser_bridge_rejects_target_drift() -> None:
    bridge = BrowserBridge()

    async def fake_command(*args, **kwargs):
        return {
            "ok": True,
            "data": {"tab_id": 9, "url": "https://example.com/b", "visible_text": "B"},
        }

    bridge.command = fake_command  # type: ignore[method-assign]
    with pytest.raises(BrowserBridgeError, match="已跳转或关闭"):
        await bridge.collect_page(target={"tab": 9, "url": "https://example.com/a"})
