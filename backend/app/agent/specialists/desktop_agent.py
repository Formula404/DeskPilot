from __future__ import annotations

from backend.app.agent.specialists.base import SpecialistAgent, SpecialistExecutionContext
from backend.app.agent.specialists.models import DesktopAgentRequest, SpecialistAgentResult, StrictRequest


class DesktopAgent(SpecialistAgent):
    name = "desktop"
    prompt_version = "desktop-agent-prompt-v1"
    request_model = DesktopAgentRequest
    allowed_tools: tuple[str, ...] = ()
    system_prompt = "Desktop Agent 尚未实现。"

    async def run(self, request: StrictRequest, context: SpecialistExecutionContext, settings) -> SpecialistAgentResult:
        return SpecialistAgentResult(
            status="unsupported",
            summary="Desktop Agent 当前尚未实现，未执行任何桌面动作。",
            unsupported_requirements=[request.objective],
            suggested_next_actions=["实现并注册受控 desktop 能力后重试"],
        )

