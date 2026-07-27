from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from backend.app.agent.intents import legacy_rule_fallback
from backend.app.agent.manager.context import ManagerContext
from backend.app.agent.manager.models import ManagerFinalResponse, ManagerPlan
from backend.app.agent.manager.prompts import MANAGER_FINAL_PROMPT, MANAGER_SYSTEM_PROMPT
from backend.app.agent.providers.structured_output import StructuredOutputError, complete_structured
from backend.app.context.security import EXTERNAL_DATA_RULE


class ManagerUnavailableError(RuntimeError):
    pass


class ManagerAgent:
    async def understand(self, context: ManagerContext, settings: Any) -> tuple[ManagerPlan, dict[str, Any]]:
        if not settings.manager.enabled:
            return self._fallback(context, "manager_disabled")
        if not settings.openai_api_key:
            return self._fallback(context, "api_key_missing")
        client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.manager.timeout_seconds,
        )
        messages = [
            {"role": "system", "content": MANAGER_SYSTEM_PROMPT + "\n" + EXTERNAL_DATA_RULE},
            {
                "role": "user",
                "content": "请理解并规划以下任务上下文。只返回规定 JSON：\n"
                + context.model_dump_json(exclude_none=False),
            },
        ]
        try:
            result = await complete_structured(
                client,
                model=settings.manager.model or settings.openai_model,
                messages=messages,
                output_model=ManagerPlan,
                configured_mode=settings.manager.structured_output_mode,
                temperature=0,
            )
        except StructuredOutputError as exc:
            fallback = self._fallback(context, "structured_output_failed")
            fallback[1]["provider_attempts"] = exc.attempts
            return fallback
        plan = ManagerPlan.model_validate(result.value)
        plan = _bind_plan_targets(plan, context)
        if (
            plan.action != "clarify"
            and plan.intent_understanding.confidence
            < settings.manager.clarification_confidence_threshold
        ):
            question = "我对当前目标或对象的理解还不够确定。请补充要处理的对象和期望结果。"
            understanding = plan.intent_understanding.model_copy(
                update={"needs_clarification": True, "clarification_question": question}
            )
            plan = ManagerPlan(
                intent_understanding=understanding,
                action="clarify",
                response=question,
                delegations=[],
            )
        return plan, {
            "fallback_reason": None,
            "structured_output_mode": result.mode,
            "structured_output_repaired": result.repaired,
            "clarification_threshold_applied": plan.action == "clarify"
            and plan.intent_understanding.confidence
            < settings.manager.clarification_confidence_threshold,
        }

    def _fallback(self, context: ManagerContext, reason: str) -> tuple[ManagerPlan, dict[str, Any]]:
        snapshot_id = context.snapshot_summary.get("snapshot_id")
        plan = legacy_rule_fallback(
            context.current_message,
            snapshot_id=str(snapshot_id) if snapshot_id else None,
            has_browser=bool(context.snapshot_summary.get("browser")),
            recent_artifact_refs=context.recent_artifact_refs,
        )
        if plan is None:
            question = (
                "语义理解模型当前不可用，而这个请求不属于可安全降级的明确低风险任务。"
                "请检查模型设置后重试，或把目标、对象和期望结果说得更具体。"
            )
            from backend.app.agent.manager.models import IntentUnderstanding

            plan = ManagerPlan(
                intent_understanding=IntentUnderstanding(
                    schema_version=1,
                    domains=["conversation"],
                    operation_classes=["inspect"],
                    goal_summary=context.current_message[:240],
                    targets=[],
                    constraints=[],
                    needs_clarification=True,
                    clarification_question=question,
                    unsupported_requirements=[],
                    confidence=0,
                ),
                action="clarify",
                response=question,
                delegations=[],
            )
        return plan, {"fallback_reason": reason, "structured_output_mode": "legacy_rule_fallback"}

    async def finalize(
        self,
        *,
        plan: ManagerPlan,
        delegation_results: list[dict[str, Any]],
        settings: Any,
    ) -> str:
        if plan.action == "clarify":
            return plan.intent_understanding.clarification_question or plan.response or "请补充任务信息。"
        if plan.action == "respond":
            return plan.response or ""
        fallback = _deterministic_final_response(plan, delegation_results)
        if not settings.openai_api_key:
            return fallback
        client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.manager.timeout_seconds,
        )
        safe_results = json.dumps(delegation_results, ensure_ascii=False, default=str)[:24000]
        try:
            result = await complete_structured(
                client,
                model=settings.manager.model or settings.openai_model,
                messages=[
                    {"role": "system", "content": MANAGER_FINAL_PROMPT + "\n" + EXTERNAL_DATA_RULE},
                    {
                        "role": "user",
                        "content": (
                            f"用户目标：{plan.intent_understanding.goal_summary}\n"
                            f"不支持项：{plan.intent_understanding.unsupported_requirements}\n"
                            f"专业 Agent 结果：{safe_results}"
                        ),
                    },
                ],
                output_model=ManagerFinalResponse,
                configured_mode=settings.manager.structured_output_mode,
                temperature=0.1,
            )
            return ManagerFinalResponse.model_validate(result.value).response
        except StructuredOutputError:
            return fallback


def _deterministic_final_response(plan: ManagerPlan, results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    artifacts: list[str] = []
    for item in results:
        agent = item.get("agent") or "specialist"
        result = item.get("result") or {}
        status = result.get("status") or item.get("status") or "failed"
        summary = result.get("summary") or "没有返回摘要。"
        lines.append(f"- {agent}（{status}）：{summary}")
        for artifact in result.get("artifacts") or []:
            path = artifact.get("path") if isinstance(artifact, dict) else None
            if path:
                artifacts.append(str(path))
    if plan.intent_understanding.unsupported_requirements:
        lines.extend(f"- 未支持：{item}" for item in plan.intent_understanding.unsupported_requirements)
    if artifacts:
        lines.append("生成的制品：" + "、".join(dict.fromkeys(artifacts)))
    return "任务执行结果：\n" + ("\n".join(lines) if lines else "没有可执行的委派。")


manager_agent = ManagerAgent()


def _bind_plan_targets(plan: ManagerPlan, context: ManagerContext) -> ManagerPlan:
    """Replace model-proposed volatile IDs with task-frozen server references."""
    snapshot_id = context.snapshot_summary.get("snapshot_id")
    has_browser = bool(context.snapshot_summary.get("browser"))
    recent_paths = [
        str(item.get("path"))
        for item in context.recent_artifact_refs
        if isinstance(item, dict) and item.get("path")
    ]
    targets = []
    missing_bound_target = False
    for target in plan.intent_understanding.targets:
        if target.kind in {"current_browser_page", "browser_selection"}:
            if not snapshot_id or not has_browser:
                missing_bound_target = True
                targets.append(target.model_copy(update={"reference_id": None}))
            else:
                targets.append(target.model_copy(update={"reference_id": str(snapshot_id)}))
        elif target.kind == "artifact" and len(recent_paths) == 1:
            targets.append(target.model_copy(update={"reference_id": recent_paths[0]}))
        else:
            targets.append(target)
    understanding = plan.intent_understanding.model_copy(update={"targets": targets})
    web_delegation_without_target = (
        plan.action == "delegate"
        and any(item.agent == "web" for item in plan.delegations)
        and (not snapshot_id or not has_browser)
    )
    if (missing_bound_target or web_delegation_without_target) and plan.action == "delegate":
        question = "任务没有绑定可用的浏览器目标，请打开目标网页并重新提交。"
        understanding = understanding.model_copy(
            update={"needs_clarification": True, "clarification_question": question}
        )
        return ManagerPlan(
            intent_understanding=understanding,
            action="clarify",
            response=question,
            delegations=[],
        )
    return plan.model_copy(update={"intent_understanding": understanding})
