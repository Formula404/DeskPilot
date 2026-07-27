from __future__ import annotations

import re

from backend.app.agent.specialists.base import SpecialistAgent, SpecialistExecutionContext
from backend.app.agent.specialists.models import KnowledgeAgentRequest, SpecialistAgentResult, StrictRequest


class KnowledgeAgent(SpecialistAgent):
    name = "knowledge"
    prompt_version = "knowledge-agent-prompt-v1"
    request_model = KnowledgeAgentRequest
    allow_no_tool_response = True
    allowed_tools = (
        "knowledge.ingest_current_page",
        "knowledge.ingest_file",
        "knowledge.ingest_text",
        "knowledge.search",
        "knowledge.answer",
        "knowledge.compile_source",
        "knowledge.review_proposal",
        "knowledge.lint",
        "knowledge.semantic_lint",
        "knowledge.rebuild_index",
    )
    system_prompt = (
        "你是 DeskPilot 的 Knowledge Agent。只操作本地知识库白名单工具。"
        "查询优先使用 knowledge_answer 并保留来源；入库时根据来源选择 current_page、file 或 text。"
        "重建索引和审核提案必须依赖服务端确认，绝不能自行跳过。不要调用其他专业 Agent。"
    )

    async def run_fallback(
        self, request: StrictRequest, context: SpecialistExecutionContext
    ) -> SpecialistAgentResult:
        text = request.objective
        lowered = text.lower()
        tool = "knowledge.answer"
        arguments: dict = {}
        if any(word in lowered for word in ("加入知识库", "存入知识库", "归档", "收藏到知识库", "导入知识库")):
            file_match = re.search(r"[\"']([^\"']+\.(?:md|txt|pdf|docx|png|jpe?g))[\"']", text, re.IGNORECASE)
            tool = "knowledge.ingest_file" if file_match else "knowledge.ingest_current_page"
            arguments = {"path": file_match.group(1)} if file_match else {}
        elif "重建" in text:
            tool = "knowledge.rebuild_index"
        elif any(word in text for word in ("语义", "矛盾", "孤立页面", "知识空白")):
            tool = "knowledge.semantic_lint"
        elif any(word in text for word in ("检查", "断链", "健康")):
            tool = "knowledge.lint"
        elif re.search(r"prop_[A-Za-z0-9_-]+", text):
            match = re.search(r"prop_[A-Za-z0-9_-]+", text)
            tool = "knowledge.review_proposal"
            arguments = {
                "proposal_id": match.group(0) if match else "",
                "decision": "reject" if any(word in text for word in ("拒绝", "驳回")) else "accept",
            }
        else:
            query = re.sub(
                r"^(请|帮我|麻烦)?\s*(在|从|用|根据)?\s*(我的)?\s*(知识库(?:里|中)?|资料里?)\s*(查一下|查询|搜索|回答)?[：:，,\s]*",
                "",
                text,
            ).strip()
            arguments = {"query": query or text}
        result, observation, _ = await self.execute_fallback_tool(tool, arguments, request, context)
        data = result.data or {}
        summary = str(data.get("answer") or result.message)
        return SpecialistAgentResult(
            status="completed" if result.ok else "needs_input" if result.error and result.error.code == "APPROVAL_REQUIRED" else "failed",
            summary=summary,
            artifacts=[item.model_dump() for item in result.artifacts],
            observations=[observation],
            source_refs=[str(value) for key in ("source_id", "snapshot_id") if (value := data.get(key))],
            missing_inputs=["用户明确确认"] if result.error and result.error.code == "APPROVAL_REQUIRED" else [],
        )
