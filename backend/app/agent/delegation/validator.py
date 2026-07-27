from __future__ import annotations

from backend.app.agent.delegation.dependency_graph import validate_acyclic
from backend.app.agent.delegation.models import DelegationRecord


class DelegationValidationError(ValueError):
    pass


class DelegationValidator:
    def validate_plan(
        self,
        records: list[DelegationRecord],
        *,
        available_agents: set[str],
        max_delegations: int,
    ) -> None:
        if len(records) > max_delegations:
            raise DelegationValidationError(
                f"委派数量 {len(records)} 超过上限 {max_delegations}。"
            )
        unavailable = sorted({record.agent for record in records} - available_agents)
        if unavailable:
            raise DelegationValidationError(f"专业 Agent 当前不可用：{unavailable}")
        try:
            validate_acyclic(records)
        except ValueError as exc:
            raise DelegationValidationError(str(exc)) from exc

    def validate_execution(
        self,
        record: DelegationRecord,
        records: list[DelegationRecord],
    ) -> None:
        if record.status != "pending":
            raise DelegationValidationError(f"委派 {record.id} 当前状态不允许执行：{record.status}")
        by_id = {item.id: item for item in records}
        for dependency in record.depends_on:
            if dependency not in by_id or by_id[dependency].status not in {"completed", "partial"}:
                raise DelegationValidationError(f"委派 {record.id} 的依赖 {dependency} 尚未完成。")


delegation_validator = DelegationValidator()
