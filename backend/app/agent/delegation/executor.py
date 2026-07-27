from __future__ import annotations

import re
from typing import Any

from backend.app.agent.delegation.models import DelegationRecord
from backend.app.agent.manager.models import IntentUnderstanding
from backend.app.agent.specialists.base import SpecialistExecutionContext
from backend.app.agent.specialists.models import (
    DesktopAgentRequest,
    FileAgentRequest,
    KnowledgeAgentRequest,
    SpecialistAgentResult,
    StrictRequest,
    WebAgentRequest,
)
from backend.app.agent.specialists.registry import specialist_registry
from backend.app.context.models import ContextBundle
from backend.app.context.service import context_builder


def _constraint(understanding: IntentUnderstanding, name: str) -> str | None:
    for item in understanding.constraints:
        if item.name == name:
            return item.value
    return None


def build_specialist_request(
    record: DelegationRecord,
    understanding: IntentUnderstanding,
    bundle: ContextBundle,
) -> StrictRequest:
    snapshot = bundle.get("snapshot") or {}
    if record.agent == "web":
        return WebAgentRequest(
            objective=record.objective,
            snapshot_id=str(snapshot.get("id") or ""),
            selection_required=any(target.kind == "browser_selection" for target in understanding.targets),
            expected_output=record.expected_output,
            input_artifact_refs=record.input_refs,
        )
    if record.agent == "knowledge":
        proposal_match = re.search(r"prop_[A-Za-z0-9_-]+", record.objective)
        query = record.objective if "search" in understanding.operation_classes else None
        return KnowledgeAgentRequest(
            objective=record.objective,
            source_refs=record.input_refs,
            query=query,
            proposal_id=proposal_match.group(0) if proposal_match else None,
            expected_output=record.expected_output,
        )
    if record.agent == "file":
        return FileAgentRequest(
            objective=record.objective,
            source_refs=record.input_refs,
            target_format=_constraint(understanding, "file_format"),
            preferred_filename=_constraint(understanding, "filename"),
            expected_output=record.expected_output,
        )
    application = next(
        (target.description for target in understanding.targets if target.kind == "desktop_application"),
        None,
    )
    return DesktopAgentRequest(
        objective=record.objective,
        application_name=application,
        target_window_id=None,
        expected_output=record.expected_output,
    )


async def execute_delegation(
    record: DelegationRecord,
    *,
    records: list[DelegationRecord],
    understanding: IntentUnderstanding,
    task_id: str,
    user_input: str,
    settings: Any,
    start_step_index: int,
    on_step_recorded: Any = None,
) -> tuple[DelegationRecord, int]:
    dependency_results = [
        {
            "delegation_id": item.id,
            "agent": item.agent,
            "status": item.status,
            "result": item.result,
        }
        for item in records
        if item.id in record.depends_on
    ]
    agent = specialist_registry.get(record.agent)
    try:
        specialist_bundle = await context_builder.build(
            task_id=task_id,
            agent=record.agent,
            capabilities=agent.capability_names(),
            token_budget=9000,
        )
    except Exception as exc:
        result = SpecialistAgentResult(
            status="failed",
            summary=f"{record.agent} Agent 上下文装配失败：{exc}",
        )
        return record.model_copy(
            update={"status": result.status, "result": result.model_dump()}
        ), start_step_index
    request = build_specialist_request(record, understanding, specialist_bundle)
    execution_context = SpecialistExecutionContext(
        task_id=task_id,
        user_input=user_input,
        context_bundle=specialist_bundle,
        dependency_results=dependency_results,
        start_step_index=start_step_index,
        on_step_recorded=on_step_recorded,
    )
    result = await agent.run(request, execution_context, settings)
    refs = [*result.source_refs]
    refs.extend(
        str(artifact.get("path"))
        for artifact in result.artifacts
        if isinstance(artifact, dict) and artifact.get("path")
    )
    return record.model_copy(
        update={
            "status": result.status,
            "result_refs": list(dict.fromkeys(refs)),
            "result": result.model_dump(),
        }
    ), execution_context.start_step_index
