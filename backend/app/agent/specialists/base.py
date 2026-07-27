from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.app.agent.specialists.models import SpecialistAgentResult, StrictRequest
from backend.app.agent.tool_calling import (
    ToolCallingError,
    _observation_for_model,
    _record_task_step,
    run_tool_calling_agent,
)
from backend.app.context.models import ContextBundle
from backend.app.context.runtime_binding import bind_browser_target, reset_browser_target
from backend.app.context.service import browser_target
from backend.app.schemas.common import ToolResult
from backend.app.tools.registry import tool_registry


@dataclass
class SpecialistExecutionContext:
    task_id: str
    user_input: str
    context_bundle: ContextBundle
    dependency_results: list[dict[str, Any]] = field(default_factory=list)
    start_step_index: int = 1
    on_step_recorded: Any = None


class SpecialistAgent:
    name: str
    prompt_version: str
    allowed_tools: tuple[str, ...]
    system_prompt: str
    request_model: type[StrictRequest]
    allow_no_tool_response: bool = False

    def capability_names(self) -> list[str]:
        return [name for name in self.allowed_tools if name in {item.name for item in tool_registry.list()}]

    async def run(
        self,
        request: StrictRequest,
        context: SpecialistExecutionContext,
        settings: Any,
    ) -> SpecialistAgentResult:
        specialist_settings = getattr(settings.specialists, self.name)
        if not settings.openai_api_key:
            return await self.run_fallback(request, context)
        try:
            raw = await run_tool_calling_agent(
                task_id=context.task_id,
                user_input=request.objective,
                allowed_tools=self.capability_names(),
                system_prompt=self.system_prompt,
                max_steps=specialist_settings.max_tool_steps,
                caller=f"{self.name}_agent",
                on_step_recorded=context.on_step_recorded,
                start_step_index=context.start_step_index,
                context_bundle=context.context_bundle,
                model=specialist_settings.model or settings.openai_model,
                timeout_seconds=specialist_settings.timeout_seconds,
                task_context={
                    "request": request.model_dump(),
                    "dependency_results": context.dependency_results,
                },
                confirmation_resolver=lambda tool, arguments: self.is_confirmed(
                    tool, arguments, request.objective
                ),
                allow_no_tool_response=self.allow_no_tool_response,
            )
        except ToolCallingError as exc:
            return SpecialistAgentResult(status="failed", summary=str(exc))
        if raw.get("cancelled"):
            return SpecialistAgentResult(status="cancelled", summary="任务已取消。")
        execution_next_index = int(raw.get("step_count") or context.start_step_index) + 1
        context.start_step_index = execution_next_index
        observations = list(raw.get("observations") or [])
        successful = [item for item in observations if (item.get("observation") or {}).get("ok")]
        status = "completed" if successful or raw.get("answered_without_tool") else "failed"
        source_refs = [
            ref
            for item in successful
            for ref in ((item.get("observation") or {}).get("source_ids") or [])
        ]
        return SpecialistAgentResult(
            status=status,
            summary=raw.get("final_response") or ("领域任务已完成。" if successful else "领域任务未完成。"),
            artifacts=list(raw.get("artifacts") or []),
            observations=observations,
            source_refs=list(dict.fromkeys(source_refs)),
            suggested_next_actions=[] if status == "completed" else ["检查失败 observation 后重试"],
        )

    async def run_fallback(
        self, request: StrictRequest, context: SpecialistExecutionContext
    ) -> SpecialistAgentResult:
        return SpecialistAgentResult(
            status="unsupported",
            summary=f"{self.name} Agent 无模型降级能力。",
            unsupported_requirements=[request.objective],
        )

    def is_confirmed(self, tool_name: str, arguments: dict[str, Any], objective: str) -> bool:
        text = objective.strip()
        if tool_name == "knowledge.review_proposal":
            proposal_id = str(arguments.get("proposal_id") or "")
            return bool(proposal_id and proposal_id in text and re.search(r"接受|同意|批准|拒绝|驳回", text))
        if tool_name == "knowledge.rebuild_index":
            return "确认" in text and "重建" in text
        return False

    async def execute_fallback_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        request: StrictRequest,
        context: SpecialistExecutionContext,
    ) -> tuple[ToolResult, dict[str, Any], int]:
        token = bind_browser_target(browser_target(context.context_bundle.get("snapshot")))
        try:
            result = await tool_registry.call(
                tool_name,
                arguments,
                caller=f"{self.name}_agent",
                confirmed=self.is_confirmed(tool_name, arguments, request.objective),
            )
        finally:
            reset_browser_target(token)
        observation = _observation_for_model(result, request.objective)
        observation["tool"] = tool_name
        step_index = context.start_step_index
        step = _record_task_step(
            task_id=context.task_id,
            step_index=step_index,
            step_type="tool",
            name=tool_name.replace(".", "_"),
            status="completed" if result.ok else "failed",
            input_data={"arguments": arguments, "fallback": True},
            output_data=observation,
        )
        if context.on_step_recorded:
            await context.on_step_recorded(step)
        context.start_step_index += 1
        return result, {"tool": tool_name, "observation": observation}, step_index
