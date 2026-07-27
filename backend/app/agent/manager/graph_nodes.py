from __future__ import annotations

import re
import time
from typing import Any

from backend.app.agent.delegation.dependency_graph import (
    all_terminal,
    mark_blocked_delegations,
    ready_delegations,
)
from backend.app.agent.delegation.executor import execute_delegation
from backend.app.agent.delegation.models import DelegationRecord
from backend.app.agent.delegation.validator import DelegationValidationError, delegation_validator
from backend.app.agent.manager.context import ManagerContext, build_manager_context
from backend.app.agent.manager.manager import manager_agent
from backend.app.agent.manager.models import IntentUnderstanding, ManagerPlan, TargetReference
from backend.app.agent.manager.prompts import MANAGER_PROMPT_VERSION
from backend.app.agent.specialists.registry import specialist_registry
from backend.app.agent.state import AgentState
from backend.app.context.service import context_builder
from backend.app.core.security import contains_secret
from backend.app.db.repository import (
    add_task_step,
    get_task,
    save_task_checkpoint,
    update_task,
    update_task_manager_trace,
)
from backend.app.settings.service import get_runtime_settings


def _next_step_index(state: AgentState) -> int:
    return int(state.get("step_count") or 0) + 1


async def _publish(state: AgentState, step: dict[str, Any]) -> None:
    callback = state.get("publish_step")
    if callback:
        await callback(step)


async def _record_step(
    state: AgentState,
    *,
    step_index: int,
    step_type: str,
    name: str,
    status: str,
    input_data: Any = None,
    output_data: Any = None,
) -> None:
    add_task_step(
        state["task_id"],
        step_index=step_index,
        step_type=step_type,
        name=name,
        status=status,
        input_data=input_data,
        output_data=output_data,
    )
    await _publish(
        state,
        {
            "step_index": step_index,
            "type": step_type,
            "name": name,
            "status": status,
            "input": input_data,
            "output": output_data,
        },
    )


async def build_manager_context_node(state: AgentState) -> AgentState:
    if state.get("error"):
        return state
    try:
        bundle = await context_builder.build(task_id=state["task_id"], agent="manager", token_budget=6000)
        context = build_manager_context(
            state["user_input"],
            bundle,
            available_agents=specialist_registry.names(),
            capability_summary=specialist_registry.capability_summary(),
        )
    except Exception as exc:
        return {**state, "error": f"Manager 上下文装配失败：{exc}"}
    step_index = _next_step_index(state)
    await _record_step(
        state,
        step_index=step_index,
        step_type="context",
        name="build_manager_context",
        status="completed",
        output_data={
            "snapshot_summary": context.snapshot_summary,
            "available_agents": context.available_agents,
            "capability_counts": {name: len(items) for name, items in context.capability_summary.items()},
            "budget": bundle.get("budget"),
        },
    )
    next_state: AgentState = {
        **state,
        "context": bundle,
        "manager_context": context.model_dump(),
        "step_count": step_index,
        "manager_turn_count": 0,
        "delegations": [],
        "unresolved_goals": [],
    }
    save_task_checkpoint(state["task_id"], "build_manager_context", next_state)
    return next_state


async def manager_node(state: AgentState) -> AgentState:
    if state.get("error") or state.get("cancelled"):
        return state
    settings = get_runtime_settings()
    turn_count = int(state.get("manager_turn_count") or 0) + 1
    if turn_count > settings.manager.max_manager_turns:
        plan = ManagerPlan.model_validate(state["manager_plan"])
        records = [DelegationRecord.model_validate(item) for item in state.get("delegations") or []]
        response = await manager_agent.finalize(
            plan=plan,
            delegation_results=[item.model_dump() for item in records],
            settings=settings,
        )
        return {
            **state,
            "manager_turn_count": turn_count,
            "final_response": response + "\nManager 已达到本轮循环上限，未继续发起委派。",
            "unresolved_goals": [item.objective for item in records if item.status == "pending"],
        }

    if not state.get("manager_plan"):
        started = time.perf_counter()
        context = ManagerContext.model_validate(state["manager_context"])
        memory_match = re.search(r"(?:请)?记住[：:,，\s]*(.+)", state.get("user_input", "").strip())
        secret_memory = (memory_match.group(1).strip() if memory_match else "")
        if secret_memory and contains_secret(secret_memory):
            refusal = "这段内容看起来包含密钥或认证信息，我不会把它发送给模型或写入长期记忆。"
            plan = ManagerPlan(
                intent_understanding=IntentUnderstanding(
                    schema_version=1,
                    domains=["conversation"],
                    operation_classes=["save"],
                    goal_summary="拒绝将 Secret 写入长期记忆",
                    targets=[TargetReference(
                        kind="conversation",
                        reference_id=state.get("turn_id"),
                        description="当前用户消息",
                    )],
                    constraints=[],
                    needs_clarification=False,
                    clarification_question=None,
                    unsupported_requirements=["Secret 不能写入长期记忆"],
                    confidence=1,
                ),
                action="respond",
                response=refusal,
                delegations=[],
            )
            metadata = {
                "fallback_reason": "secret_memory_blocked",
                "structured_output_mode": "deterministic_safety_precheck",
            }
        else:
            plan, metadata = await manager_agent.understand(context, settings)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        records = [
            DelegationRecord(
                id=item.id,
                agent=item.agent,
                objective=item.objective,
                depends_on=item.depends_on,
                input_refs=item.input_refs,
                expected_output=item.expected_output,
            )
            for item in plan.delegations
        ]
        try:
            delegation_validator.validate_plan(
                records,
                available_agents=set(specialist_registry.names()),
                max_delegations=settings.manager.max_delegations,
            )
        except DelegationValidationError as exc:
            records = []
            plan = plan.model_copy(update={"action": "respond", "response": f"任务规划未通过安全验证：{exc}", "delegations": []})
        understanding = plan.intent_understanding
        primary_intent = ",".join(understanding.domains) or "conversation"
        update_task(state["task_id"], intent=primary_intent, status="running")
        update_task_manager_trace(
            state["task_id"],
            manager_model=settings.manager.model or settings.openai_model,
            manager_prompt_version=MANAGER_PROMPT_VERSION,
            intent_schema_version=understanding.schema_version,
            intent_understanding=understanding.model_dump(),
            manager_latency_ms=elapsed_ms,
            manager_fallback_reason=metadata.get("fallback_reason"),
            delegation_count=len(records),
        )
        step_index = _next_step_index(state)
        await _record_step(
            state,
            step_index=step_index,
            step_type="manager",
            name="manager.understand",
            status="completed",
            input_data={"message_id": state.get("turn_id"), "prompt_version": MANAGER_PROMPT_VERSION},
            output_data={
                "intent_understanding": understanding.model_dump(),
                "action": plan.action,
                "delegations": [item.model_dump() for item in records],
                "provider": metadata,
                "latency_ms": elapsed_ms,
            },
        )
        next_state: AgentState = {
            **state,
            "intent": primary_intent,
            "intent_understanding": understanding.model_dump(),
            "manager_plan": plan.model_dump(),
            "manager_metadata": metadata,
            "delegations": [item.model_dump() for item in records],
            "manager_turn_count": turn_count,
            "step_count": step_index,
        }
        if plan.action in {"clarify", "respond"}:
            response = await manager_agent.finalize(plan=plan, delegation_results=[], settings=settings)
            next_state["final_response"] = response
            if plan.action == "clarify":
                clarification_step = step_index + 1
                await _record_step(
                    state,
                    step_index=clarification_step,
                    step_type="manager",
                    name="manager.clarify",
                    status="completed",
                    output_data={"question": response},
                )
                next_state["step_count"] = clarification_step
        save_task_checkpoint(state["task_id"], "manager.understand", next_state)
        return next_state

    plan = ManagerPlan.model_validate(state["manager_plan"])
    records = [DelegationRecord.model_validate(item) for item in state.get("delegations") or []]
    records = mark_blocked_delegations(records)
    if all_terminal(records):
        response = await manager_agent.finalize(
            plan=plan,
            delegation_results=[item.model_dump() for item in records],
            settings=settings,
        )
        step_index = _next_step_index(state)
        await _record_step(
            state,
            step_index=step_index,
            step_type="manager",
            name="manager.synthesize",
            status="completed",
            output_data={"final_response": response, "delegation_count": len(records)},
        )
        return {
            **state,
            "delegations": [item.model_dump() for item in records],
            "manager_turn_count": turn_count,
            "step_count": step_index,
            "final_response": response,
            "unresolved_goals": [item.objective for item in records if item.status != "completed"],
        }
    ready = ready_delegations(records)
    if not ready:
        return {
            **state,
            "delegations": [item.model_dump() for item in records],
            "manager_turn_count": turn_count,
            "final_response": "委派依赖无法继续执行，已停止任务并保留当前结果。",
            "unresolved_goals": [item.objective for item in records if item.status == "pending"],
        }
    return {
        **state,
        "delegations": [item.model_dump() for item in records],
        "active_delegation_id": ready[0].id,
        "manager_turn_count": turn_count,
    }


async def execute_agent_tool_node(state: AgentState) -> AgentState:
    active_id = state.get("active_delegation_id")
    records = [DelegationRecord.model_validate(item) for item in state.get("delegations") or []]
    record = next((item for item in records if item.id == active_id), None)
    if record is None:
        return {**state, "error": "找不到当前委派记录。"}
    task = get_task(state["task_id"])
    if task and task.get("status") == "cancelled":
        return {**state, "cancelled": True, "active_delegation_id": None}
    try:
        delegation_validator.validate_execution(record, records)
    except DelegationValidationError as exc:
        return {**state, "error": str(exc), "active_delegation_id": None}
    await _publish(
        state,
        {
            "step_index": _next_step_index(state),
            "type": "manager",
            "name": f"manager.delegate.{record.agent}",
            "status": "running",
            "input": {"delegation_id": record.id, "objective": record.objective},
        },
    )
    settings = get_runtime_settings()
    understanding = IntentUnderstanding.model_validate(state["intent_understanding"])
    completed, next_index = await execute_delegation(
        record,
        records=records,
        understanding=understanding,
        task_id=state["task_id"],
        user_input=state["user_input"],
        settings=settings,
        start_step_index=_next_step_index(state),
        on_step_recorded=lambda step: _publish(state, step),
    )
    records = [completed if item.id == completed.id else item for item in records]
    result_step = max(next_index, _next_step_index(state))
    await _record_step(
        state,
        step_index=result_step,
        step_type="specialist",
        name="specialist.result",
        status="completed" if completed.status in {"completed", "partial", "unsupported", "needs_input"} else "failed",
        input_data={
            "delegation_id": completed.id,
            "agent": completed.agent,
            "depends_on": completed.depends_on,
            "prompt_version": specialist_registry.get(completed.agent).prompt_version,
        },
        output_data=completed.result,
    )
    artifacts = list(state.get("artifacts") or [])
    artifacts.extend((completed.result or {}).get("artifacts") or [])
    observations = list(state.get("observations") or [])
    observations.append({
        "delegation_id": completed.id,
        "agent": completed.agent,
        "result": completed.result,
    })
    next_state: AgentState = {
        **state,
        "delegations": [item.model_dump() for item in records],
        "active_delegation_id": None,
        "step_count": result_step,
        "artifacts": artifacts,
        "observations": observations,
    }
    save_task_checkpoint(state["task_id"], f"manager.delegate.{completed.agent}", next_state)
    return next_state


def route_manager(state: AgentState) -> str:
    if state.get("error") or state.get("cancelled") or state.get("final_response"):
        return "finalize"
    if state.get("active_delegation_id"):
        return "execute_agent_tool"
    return "manager"
