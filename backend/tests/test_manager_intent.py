from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.agent.delegation.dependency_graph import ready_delegations, validate_acyclic
from backend.app.agent.delegation.models import DelegationRecord
from backend.app.agent.evaluation import evaluate_manager_cases
from backend.app.agent.graph import build_graph
from backend.app.agent.intents import legacy_rule_fallback
from backend.app.agent.manager import graph_nodes
from backend.app.agent.manager.context import ManagerContext, build_manager_context
from backend.app.agent.manager.manager import _bind_plan_targets
from backend.app.agent.manager.models import (
    IntentUnderstanding,
    ManagerPlan,
    PlannedDelegation,
    TargetReference,
)
from backend.app.agent.providers.structured_output import complete_structured
from backend.app.agent import tool_calling
from backend.app.agent.specialists import base as specialist_base
from backend.app.agent.specialists.base import SpecialistExecutionContext
from backend.app.agent.specialists.knowledge_agent import KnowledgeAgent
from backend.app.agent.specialists.models import KnowledgeAgentRequest, SpecialistAgentResult
from backend.app.agent.specialists.registry import specialist_registry
from backend.app.core.config import get_settings as get_core_settings
from backend.app.db.connection import init_db
from backend.app.db.repository import (
    add_message,
    create_session,
    create_task,
    get_task,
    list_task_steps,
    save_context_snapshot,
)
from backend.app.memory.repository import list_memories, save_memory
from backend.app.schemas.common import ToolResult
from backend.app.tools.base import ToolDefinition
from backend.app.tools.registry import ToolRegistry
from backend.app.main import app


@pytest.fixture
def manager_data_dir(tmp_path):
    settings = get_core_settings()
    original = settings.data_dir
    settings.data_dir = tmp_path / "data"
    init_db()
    try:
        yield settings.data_dir
    finally:
        settings.data_dir = original


def _understanding(domains: list[str]) -> IntentUnderstanding:
    return IntentUnderstanding(
        schema_version=1,
        domains=domains,
        operation_classes=["read", "transform", "save", "create"],
        goal_summary="总结网页，保存知识库并导出 Markdown",
        targets=[
            TargetReference(
                kind="current_browser_page",
                reference_id="snapshot-test",
                description="任务绑定页面",
            )
        ],
        constraints=[],
        needs_clarification=False,
        clarification_question=None,
        unsupported_requirements=[],
        confidence=0.95,
    )


def test_intent_understanding_forbids_extra_and_invalid_confidence() -> None:
    payload = _understanding(["web"]).model_dump()
    payload["confidence"] = 1.2
    with pytest.raises(ValidationError):
        IntentUnderstanding.model_validate(payload)
    payload["confidence"] = 0.8
    payload["hidden_reasoning"] = "must not be accepted"
    with pytest.raises(ValidationError):
        IntentUnderstanding.model_validate(payload)


def test_legacy_fallback_handles_synonym_but_rejects_compound_task() -> None:
    single = legacy_rule_fallback(
        "帮我消化一下眼前这篇文章",
        snapshot_id="snapshot-1",
        has_browser=True,
    )
    assert single is not None
    assert single.action == "delegate"
    assert single.intent_understanding.domains == ["web"]

    compound = legacy_rule_fallback(
        "总结当前网页并导入知识库，再保存 Markdown",
        snapshot_id="snapshot-1",
        has_browser=True,
    )
    assert compound is not None
    assert compound.action == "clarify"
    assert not compound.delegations


def test_dependency_graph_only_releases_satisfied_delegations() -> None:
    records = [
        DelegationRecord(id="delegation_1", agent="web", objective="summary", expected_output="summary"),
        DelegationRecord(
            id="delegation_2",
            agent="file",
            objective="markdown",
            depends_on=["delegation_1"],
            expected_output="file",
        ),
    ]
    validate_acyclic(records)
    assert [item.id for item in ready_delegations(records)] == ["delegation_1"]
    completed = records[0].model_copy(update={"status": "completed"})
    assert [item.id for item in ready_delegations([completed, records[1]])] == ["delegation_2"]

    cycle = [
        records[0].model_copy(update={"depends_on": ["delegation_2"]}),
        records[1],
    ]
    with pytest.raises(ValueError, match="环"):
        validate_acyclic(cycle)


def test_manager_rebinds_model_target_to_frozen_snapshot() -> None:
    plan = ManagerPlan(
        intent_understanding=_understanding(["web"]),
        action="delegate",
        response=None,
        delegations=[
            PlannedDelegation(
                id="delegation_1",
                agent="web",
                objective="总结网页",
                depends_on=[],
                input_refs=["hallucinated"],
                expected_output="摘要",
            )
        ],
    )
    context = ManagerContext(
        current_message="总结网页",
        recent_messages=[],
        conversation_summary=None,
        snapshot_summary={
            "snapshot_id": "snapshot-real",
            "browser": {"tab_id": "1", "url": "https://example.com"},
        },
        recent_artifact_refs=[],
        available_agents=["web"],
        capability_summary={"web": ["browser.collect_current_page"]},
        user_preferences=[],
    )
    bound = _bind_plan_targets(plan, context)
    assert bound.intent_understanding.targets[0].reference_id == "snapshot-real"

    without_browser = _bind_plan_targets(
        plan,
        context.model_copy(update={"snapshot_summary": {}}),
    )
    assert without_browser.action == "clarify"
    assert without_browser.delegations == []


@pytest.mark.asyncio
async def test_structured_output_repairs_invalid_json_once() -> None:
    valid = ManagerPlan(
        intent_understanding=IntentUnderstanding(
            schema_version=1,
            domains=["conversation"],
            operation_classes=["read"],
            goal_summary="问候",
            targets=[],
            constraints=[],
            needs_clarification=False,
            clarification_question=None,
            unsupported_requirements=[],
            confidence=0.9,
        ),
        action="respond",
        response="你好",
        delegations=[],
    ).model_dump_json()
    calls = 0

    async def create(**kwargs):
        nonlocal calls
        calls += 1
        content = "not json" if calls == 1 else valid
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    result = await complete_structured(
        client,
        model="test",
        messages=[{"role": "user", "content": "hello"}],
        output_model=ManagerPlan,
        configured_mode="native",
    )
    assert result.repaired is True
    assert result.value.action == "respond"
    assert calls == 2


@pytest.mark.asyncio
async def test_structured_output_auto_falls_back_when_native_mode_is_unsupported() -> None:
    valid = ManagerPlan(
        intent_understanding=IntentUnderstanding(
            schema_version=1,
            domains=["conversation"],
            operation_classes=["read"],
            goal_summary="问候",
            targets=[],
            constraints=[],
            needs_clarification=False,
            clarification_question=None,
            unsupported_requirements=[],
            confidence=0.9,
        ),
        action="respond",
        response="你好",
        delegations=[],
    ).model_dump_json()

    async def create(**kwargs):
        if (kwargs.get("response_format") or {}).get("type") == "json_schema":
            raise RuntimeError("json_schema unsupported")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=valid))]
        )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    result = await complete_structured(
        client,
        model="test",
        messages=[{"role": "user", "content": "hello"}],
        output_model=ManagerPlan,
        configured_mode="auto",
    )
    assert result.mode == "json_mode"


@pytest.mark.asyncio
async def test_tool_registry_enforces_caller_schema_and_confirmation() -> None:
    calls = 0

    async def handler(payload: dict) -> ToolResult:
        nonlocal calls
        calls += 1
        return ToolResult(ok=True, data={"accepted": payload["value"]}, message="ok")

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="knowledge.review_test",
            domain="knowledge",
            description="test",
            input_schema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
            risk_level="medium",
            required_permissions=["knowledge:review"],
            allowed_callers=["knowledge_agent"],
            handler=handler,
        )
    )
    forbidden = await registry.call("knowledge.review_test", {"value": "x"}, caller="web_agent")
    invalid = await registry.call("knowledge.review_test", {"bad": "x"}, caller="knowledge_agent")
    approval = await registry.call("knowledge.review_test", {"value": "x"}, caller="knowledge_agent")
    completed = await registry.call(
        "knowledge.review_test", {"value": "x"}, caller="knowledge_agent", confirmed=True
    )
    assert forbidden.error and forbidden.error.code == "TOOL_CALLER_FORBIDDEN"
    assert invalid.error and invalid.error.code == "TOOL_ARGUMENT_INVALID"
    assert approval.error and approval.error.code == "APPROVAL_REQUIRED"
    assert completed.ok and calls == 1


@pytest.mark.asyncio
async def test_agent_browser_capability_requires_frozen_target() -> None:
    async def handler(payload: dict) -> ToolResult:
        return ToolResult(ok=True, data={}, message="should not run")

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="browser.test_read",
            domain="web",
            description="test",
            risk_level="low",
            required_permissions=["browser_context:read"],
            allowed_callers=["web_agent"],
            handler=handler,
        )
    )
    result = await registry.call("browser.test_read", {}, caller="web_agent")
    assert result.error and result.error.code == "BOUND_BROWSER_TARGET_REQUIRED"


@pytest.mark.asyncio
async def test_manager_graph_uses_audited_safe_fallback_without_api_key(manager_data_dir) -> None:
    task_id = create_task("记住我默认使用中文")
    result = await build_graph().ainvoke(
        {
            "task_id": task_id,
            "user_input": "记住我默认使用中文",
            "observations": [],
            "artifacts": [],
        }
    )
    task = get_task(task_id)
    assert result["final_response"].startswith("好的")
    assert task["status"] == "completed"
    assert task["manager_fallback_reason"] == "api_key_missing"
    assert any(item["name"] == "manager.understand" for item in list_task_steps(task_id))


@pytest.mark.asyncio
async def test_secret_memory_is_blocked_before_manager_and_never_persisted(manager_data_dir, monkeypatch) -> None:
    task_id = create_task("记住我的 OpenAI API 密钥是 sk-abcdefghijklmnop")

    async def manager_must_not_run(*args, **kwargs):
        raise AssertionError("Secret memory request must be blocked before the model call")

    monkeypatch.setattr(graph_nodes.manager_agent, "understand", manager_must_not_run)
    result = await build_graph().ainvoke(
        {
            "task_id": task_id,
            "user_input": "记住我的 OpenAI API 密钥是 sk-abcdefghijklmnop",
            "observations": [],
            "artifacts": [],
        }
    )
    assert "不会把它发送给模型或写入长期记忆" in result["final_response"]
    assert list_memories() == []
    assert get_task(task_id)["manager_fallback_reason"] == "secret_memory_blocked"
    assert any(item["name"] == "reject_secret_memory" for item in list_task_steps(task_id))


@pytest.mark.asyncio
async def test_manager_context_contains_budgeted_relevant_memory(manager_data_dir) -> None:
    save_memory(kind="preference", content="我的笔记应用是 Obsidian")
    task_id = create_task("调用我的笔记应用")
    bundle = await graph_nodes.context_builder.build(task_id=task_id, agent="manager")
    context = build_manager_context(
        "调用我的笔记应用",
        bundle,
        available_agents=specialist_registry.names(),
        capability_summary=specialist_registry.capability_summary(),
    )
    assert any("Obsidian" in item["content"] for item in context.relevant_memories)


@pytest.mark.asyncio
async def test_tool_runner_allows_same_arguments_after_an_intervening_model_round(
    manager_data_dir, monkeypatch
) -> None:
    task_id = create_task("refresh")
    responses = [
        ("test_refresh", "call-1"),
        ("test_process", "call-2"),
        ("test_refresh", "call-3"),
        (None, None),
    ]

    async def create(**kwargs):
        name, call_id = responses.pop(0)
        if name is None:
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="done", tool_calls=[]))]
            )
        call = SimpleNamespace(
            id=call_id,
            type="function",
            function=SimpleNamespace(name=name, arguments="{}"),
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[call]))]
        )

    called: list[str] = []

    class FakeRegistry:
        def openai_tools(self, allowed_names, caller=None):
            return []

        def get_by_openai_name(self, name):
            return SimpleNamespace(name=name.replace("_", ".", 1))

        async def call(self, name, arguments, **kwargs):
            called.append(name)
            return ToolResult(ok=True, data={"name": name}, message="ok")

    settings = SimpleNamespace(
        openai_api_key="configured",
        openai_base_url="https://example.com/v1",
        openai_model="test",
        request_timeout_seconds=10,
        temperature=0,
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(tool_calling, "get_settings", lambda: settings)
    monkeypatch.setattr(tool_calling, "AsyncOpenAI", lambda **kwargs: client)
    monkeypatch.setattr(tool_calling, "tool_registry", FakeRegistry())
    result = await tool_calling._run_tool_agent(
        task_id=task_id,
        user_input="refresh",
        allowed_tools=["test.refresh", "test.process"],
        system_prompt="test",
        no_tool_fallback="use a tool",
        max_steps=4,
    )
    assert called == ["test.refresh", "test.process", "test.refresh"]
    assert all(item["observation"]["ok"] for item in result["observations"])


@pytest.mark.asyncio
async def test_tool_runner_can_return_grounded_text_without_a_tool(manager_data_dir, monkeypatch) -> None:
    task_id = create_task("what do you know")

    async def create(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="来自上下文的答案", tool_calls=[]))]
        )

    class FakeRegistry:
        def openai_tools(self, allowed_names, caller=None):
            return []

    settings = SimpleNamespace(
        openai_api_key="configured",
        openai_base_url="https://example.com/v1",
        openai_model="test",
        request_timeout_seconds=10,
        temperature=0,
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(tool_calling, "get_settings", lambda: settings)
    monkeypatch.setattr(tool_calling, "AsyncOpenAI", lambda **kwargs: client)
    monkeypatch.setattr(tool_calling, "tool_registry", FakeRegistry())
    result = await tool_calling._run_tool_agent(
        task_id=task_id,
        user_input="what do you know",
        allowed_tools=[],
        system_prompt="test",
        no_tool_fallback="use a tool",
        max_steps=1,
        allow_no_tool_response=True,
    )
    assert result["final_response"] == "来自上下文的答案"
    assert result["answered_without_tool"] is True
    assert result["observations"] == []


@pytest.mark.asyncio
async def test_knowledge_agent_allows_context_only_answer_without_summary_fields(
    manager_data_dir, monkeypatch
) -> None:
    task_id = create_task("你知道关于 X 的什么？")
    captured: dict = {}

    async def run_agent(**kwargs):
        captured.update(kwargs)
        return {
            "final_response": "上下文已经提供了答案。",
            "artifacts": [],
            "observations": [],
            "step_count": 1,
            "answered_without_tool": True,
        }

    monkeypatch.setattr(specialist_base, "run_tool_calling_agent", run_agent)
    settings = SimpleNamespace(
        openai_api_key="configured",
        openai_model="test",
        specialists=SimpleNamespace(
            knowledge=SimpleNamespace(model=None, timeout_seconds=10, max_tool_steps=2)
        ),
    )
    context = SpecialistExecutionContext(
        task_id=task_id,
        user_input="你知道关于 X 的什么？",
        context_bundle={
            "snapshot": {},
            "conversation": {},
            "preferences": [],
            "memories": [],
            "knowledge": [],
            "execution": {},
            "provenance": [],
            "blocks": [{"kind": "knowledge_evidence", "content": "X 的已检索证据"}],
            "budget": {},
            "degraded": [],
        },
    )
    result = await KnowledgeAgent().run(
        KnowledgeAgentRequest(
            objective="你知道关于 X 的什么？",
            source_refs=[],
            query="X",
            proposal_id=None,
            expected_output="answer",
        ),
        context,
        settings,
    )

    assert captured["allow_no_tool_response"] is True
    assert result.status == "completed"
    assert result.summary == "上下文已经提供了答案。"


@pytest.mark.asyncio
async def test_manager_graph_executes_cross_domain_dependencies(manager_data_dir, monkeypatch) -> None:
    session_id = create_session()
    now = datetime.now(UTC)
    snapshot_id = save_context_snapshot(
        session_id=session_id,
        source="test",
        window={},
        browser={"tab_id": "1", "url": "https://example.com", "title": "Example"},
        selection={},
        attachments=[],
        sensitivity="normal",
        captured_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=10)).isoformat(),
    )
    message = "总结当前网页，存进知识库，再导出 Markdown"
    turn_id = add_message(session_id, role="user", content=message)
    task_id = create_task(
        message,
        session_id=session_id,
        turn_id=turn_id,
        context_snapshot_id=snapshot_id,
    )
    plan = ManagerPlan(
        intent_understanding=_understanding(["web", "knowledge", "file"]),
        action="delegate",
        response=None,
        delegations=[
            PlannedDelegation(
                id="delegation_1", agent="web", objective="总结当前网页",
                depends_on=[], input_refs=[snapshot_id], expected_output="摘要",
            ),
            PlannedDelegation(
                id="delegation_2", agent="knowledge", objective="保存网页和摘要",
                depends_on=["delegation_1"], input_refs=["delegation_1"], expected_output="知识来源",
            ),
            PlannedDelegation(
                id="delegation_3", agent="file", objective="导出 Markdown",
                depends_on=["delegation_1"], input_refs=["delegation_1"], expected_output="Markdown 文件",
            ),
        ],
    )

    async def fake_understand(context, settings):
        return plan, {"fallback_reason": None, "structured_output_mode": "test"}

    order: list[str] = []
    context_policy_keys: list[str] = []

    async def fake_run(request, context, settings):
        agent_name = "web" if "总结" in request.objective else "knowledge" if "保存" in request.objective else "file"
        order.append(agent_name)
        context_policy_keys.append(context.context_bundle["execution"]["context_policy_key"])
        return SpecialistAgentResult(
            status="completed",
            summary="网页摘要" if agent_name == "web" else f"{agent_name} done",
            artifacts=[{"type": "file", "path": "D:/fake/result.md"}] if agent_name == "file" else [],
            observations=[],
        )

    monkeypatch.setattr(graph_nodes.manager_agent, "understand", fake_understand)
    for name in ("web", "knowledge", "file"):
        monkeypatch.setattr(specialist_registry.get(name), "run", fake_run)

    result = await build_graph().ainvoke(
        {
            "task_id": task_id,
            "user_input": message,
            "context_snapshot_id": snapshot_id,
            "observations": [],
            "artifacts": [],
        }
    )
    assert order == ["web", "knowledge", "file"]
    assert context_policy_keys == ["agent:web", "agent:knowledge", "agent:file"]
    assert all(item["status"] == "completed" for item in result["delegations"])
    assert get_task(task_id)["status"] == "completed"
    step_names = [item["name"] for item in list_task_steps(task_id)]
    assert "manager.understand" in step_names
    assert step_names.count("specialist.result") == 3
    assert "manager.synthesize" in step_names
    trace = TestClient(app).get(f"/tasks/{task_id}/trace")
    assert trace.status_code == 200
    assert trace.json()["manager"]["delegation_count"] == 3
    assert trace.json()["intent_understanding"]["domains"] == ["web", "knowledge", "file"]


def test_manager_evaluation_metrics_fixture() -> None:
    path = Path(__file__).parent / "fixtures" / "manager_eval_cases.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    predictions = [
        {
            "domains": item["expected"]["domains"],
            "operation_classes": item["expected"]["operations"],
            "needs_clarification": item["expected"]["needs_clarification"],
        }
        for item in cases
    ]
    metrics = evaluate_manager_cases(cases, predictions)
    assert metrics == {
        "domain_micro_f1": 1.0,
        "operation_micro_f1": 1.0,
        "clarification_accuracy": 1.0,
    }
