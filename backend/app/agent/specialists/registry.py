from __future__ import annotations

from backend.app.agent.specialists.base import SpecialistAgent
from backend.app.agent.specialists.desktop_agent import DesktopAgent
from backend.app.agent.specialists.file_agent import FileAgent
from backend.app.agent.specialists.knowledge_agent import KnowledgeAgent
from backend.app.agent.specialists.web_agent import WebAgent


class SpecialistRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, SpecialistAgent] = {}

    def register(self, agent: SpecialistAgent) -> None:
        self._agents[agent.name] = agent

    def get(self, name: str) -> SpecialistAgent:
        return self._agents[name]

    def names(self) -> list[str]:
        return list(self._agents)

    def capability_summary(self) -> dict[str, list[str]]:
        return {name: agent.capability_names() for name, agent in self._agents.items()}


specialist_registry = SpecialistRegistry()
for _agent in (WebAgent(), KnowledgeAgent(), FileAgent(), DesktopAgent()):
    specialist_registry.register(_agent)
