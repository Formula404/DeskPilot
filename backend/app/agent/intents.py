from __future__ import annotations

import re

from backend.app.agent.manager.models import (
    IntentUnderstanding,
    ManagerPlan,
    PlannedDelegation,
    TargetReference,
    UserConstraint,
)


def detect_intent(message: str) -> str:
    """Compatibility-only classifier for old callers and tests.

    The Manager path never uses this value as its normal routing decision. New
    capabilities must not be added here merely to create another global label.
    """
    normalized = message.lower()
    table_keywords = ["表格", "excel", "xlsx"]
    export_keywords = ["导出", "保存", "提取", "抽取", "生成", "写入", "excel", "xlsx"]
    if any(
        keyword in normalized
        for keyword in ["接受提案", "同意提案", "批准提案", "应用提案", "拒绝提案", "驳回提案", "审核提案", "知识更新提案"]
    ):
        return "knowledge_review"
    if any(keyword in normalized for keyword in ["检查知识库", "知识库检查", "知识库健康", "知识索引", "断链"]):
        return "knowledge_maintenance"
    if any(
        keyword in normalized
        for keyword in ["加入知识库", "存入知识库", "归档当前页面", "归档当前网页", "收藏到知识库", "记住这篇", "导入文件到知识库", "导入知识库"]
    ):
        return "knowledge_ingest"
    if normalized.strip().startswith(("记住", "请记住")):
        return "memory_write"
    if any(keyword in normalized for keyword in table_keywords) and any(
        keyword in normalized for keyword in export_keywords
    ):
        return "web_table_export"
    if any(
        keyword in normalized
        for keyword in ["在知识库", "查知识库", "查询知识库", "根据我的资料", "我收集过", "知识库里", "知识库中"]
    ):
        return "knowledge_query"
    if any(keyword in normalized for keyword in ["网页", "页面", "website", "page", "总结"]):
        return "web_page_summary"
    if any(keyword in normalized for keyword in ["打开", "启动"]):
        return "desktop_app_open"
    return "general_chat"


def _target(kind: str, reference_id: str | None, description: str) -> TargetReference:
    return TargetReference(kind=kind, reference_id=reference_id, description=description)  # type: ignore[arg-type]


def _understanding(
    *,
    domains: list[str],
    operations: list[str],
    goal: str,
    targets: list[TargetReference] | None = None,
    constraints: list[UserConstraint] | None = None,
    clarification: str | None = None,
    unsupported: list[str] | None = None,
    confidence: float = 0.75,
) -> IntentUnderstanding:
    return IntentUnderstanding(
        schema_version=1,
        domains=domains,  # type: ignore[arg-type]
        operation_classes=operations,  # type: ignore[arg-type]
        goal_summary=goal,
        targets=targets or [],
        constraints=constraints or [],
        needs_clarification=clarification is not None,
        clarification_question=clarification,
        unsupported_requirements=unsupported or [],
        confidence=confidence,
    )


def legacy_rule_fallback(
    message: str,
    *,
    snapshot_id: str | None = None,
    has_browser: bool = False,
    recent_artifact_refs: list[dict] | None = None,
) -> ManagerPlan | None:
    """Return a conservative plan when the semantic model is unavailable.

    Only explicit, low-risk and single-domain requests are executable. Compound
    or ambiguous requests deliberately return a clarification/retry response.
    """
    normalized = message.strip().lower()
    if not normalized:
        return None

    domain_hits = {
        "web": any(word in normalized for word in ("网页", "页面", "这篇文章", "眼前这篇", "表格", "website")),
        "knowledge": "知识库" in normalized or "知识提案" in normalized,
        "file": any(word in normalized for word in ("markdown", "excel", "xlsx", "文件")),
        "desktop": bool(re.search(r"(?:打开|启动)\s*[^，。,.]+", normalized)),
    }
    explicit_domains = [name for name, hit in domain_hits.items() if hit]
    compound = len(explicit_domains) > 1 or bool(re.search(r"(?:并|再|然后|同时|之后|并且|以及)", normalized))
    if compound:
        question = "当前语义模型不可用，无法安全执行这个组合任务。请恢复模型服务后重试，或先只提交其中一个明确步骤。"
        understanding = _understanding(
            domains=[name for name in explicit_domains if name in {"web", "knowledge", "file", "desktop"}],
            operations=["read"],
            goal=message[:240],
            clarification=question,
            confidence=0.2,
        )
        return ManagerPlan(intent_understanding=understanding, action="clarify", response=question, delegations=[])

    if normalized.startswith(("记住", "请记住")):
        response = "好的，我会按你的明确要求记住这项信息。"
        return ManagerPlan(
            intent_understanding=_understanding(
                domains=["conversation"], operations=["save"], goal=message[:240], confidence=0.98
            ),
            action="respond",
            response=response,
            delegations=[],
        )

    if domain_hits["desktop"]:
        requirement = f"桌面应用操作尚未实现：{message[:160]}"
        return ManagerPlan(
            intent_understanding=_understanding(
                domains=["desktop"], operations=["open"], goal=message[:240],
                targets=[_target("desktop_application", None, message[:160])],
                unsupported=[requirement], confidence=0.9,
            ),
            action="respond",
            response=f"我理解你要{message.strip()}，但 Desktop Agent 当前尚未实现，不能假装已经执行。",
            delegations=[],
        )

    asks_table_export = any(word in normalized for word in ("表格", "列表", "卡片")) and any(
        word in normalized for word in ("导出", "提取", "抽取", "excel", "xlsx")
    )
    asks_page_summary = any(
        word in normalized for word in ("总结", "概括", "提炼", "消化", "主要讲", "要点")
    ) and any(word in normalized for word in ("网页", "页面", "这篇", "眼前", "当前"))
    if asks_table_export or asks_page_summary:
        if not has_browser:
            question = "提交任务时没有绑定可用网页，请打开目标网页后重新提交。"
            understanding = _understanding(
                domains=["web"], operations=["extract" if asks_table_export else "read", "create"] if asks_table_export else ["read", "transform"],
                goal=message[:240], clarification=question, confidence=0.95,
            )
            return ManagerPlan(intent_understanding=understanding, action="clarify", response=question, delegations=[])
        operations = ["extract", "create"] if asks_table_export else ["read", "transform"]
        expected = "Excel 文件" if asks_table_export else "网页摘要"
        understanding = _understanding(
            domains=["web"], operations=operations, goal=message[:240],
            targets=[_target("current_browser_page", snapshot_id, "任务提交时绑定的浏览器页面")],
            constraints=[UserConstraint(name="file_format", value="xlsx")] if asks_table_export else [],
            confidence=0.96,
        )
        return ManagerPlan(
            intent_understanding=understanding,
            action="delegate",
            response=None,
            delegations=[PlannedDelegation(
                id="delegation_1", agent="web", objective=message,
                depends_on=[], input_refs=[snapshot_id] if snapshot_id else [], expected_output=expected,
            )],
        )

    intent = detect_intent(message)
    if intent in {"knowledge_query", "knowledge_ingest", "knowledge_maintenance"}:
        file_reference = bool(re.search(r"[A-Za-z]:[\\/].+\.(?:md|txt|pdf|docx|png|jpe?g)", message, re.IGNORECASE))
        if intent == "knowledge_ingest" and not file_reference and not has_browser:
            question = "提交任务时没有绑定可入库的网页，也没有提供本地文件路径。请明确来源后重新提交。"
            return ManagerPlan(
                intent_understanding=_understanding(
                    domains=["knowledge"], operations=["save"], goal=message[:240],
                    targets=[_target("unknown", None, "待入库来源不明确")],
                    clarification=question, confidence=0.45,
                ),
                action="clarify", response=question, delegations=[],
            )
        operation = "search" if intent == "knowledge_query" else "save" if intent == "knowledge_ingest" else "inspect"
        targets = [_target("knowledge_base", None, "本地知识库")]
        refs: list[str] = []
        if intent == "knowledge_ingest" and has_browser and snapshot_id:
            targets.insert(0, _target("current_browser_page", snapshot_id, "任务提交时绑定的浏览器页面"))
            refs.append(snapshot_id)
        return ManagerPlan(
            intent_understanding=_understanding(
                domains=["knowledge"], operations=[operation], goal=message[:240],
                targets=targets, confidence=0.9,
            ),
            action="delegate",
            response=None,
            delegations=[PlannedDelegation(
                id="delegation_1", agent="knowledge", objective=message,
                depends_on=[], input_refs=refs, expected_output="知识库操作结果",
            )],
        )

    if normalized in {"处理一下这个", "导出一下", "把它发出去", "处理这个文件"}:
        question = "你希望处理或导出什么内容，以及期望的结果格式是什么？"
        return ManagerPlan(
            intent_understanding=_understanding(
                domains=["conversation"], operations=["inspect"], goal=message,
                targets=[_target("unknown", None, "指代对象不明确")], clarification=question, confidence=0.15,
            ),
            action="clarify", response=question, delegations=[],
        )

    if recent_artifact_refs and any(word in normalized for word in ("它", "刚才那个", "那个文件")):
        question = "当前语义模型不可用，无法可靠判断你要对最近制品执行什么操作；请明确说明目标格式或动作。"
        return ManagerPlan(
            intent_understanding=_understanding(
                domains=["file"], operations=["transform"], goal=message,
                targets=[_target("artifact", str(recent_artifact_refs[0].get("path") or ""), "最近生成的制品")],
                clarification=question, confidence=0.3,
            ), action="clarify", response=question, delegations=[],
        )
    return None
