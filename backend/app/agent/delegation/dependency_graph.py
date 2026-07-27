from __future__ import annotations

from backend.app.agent.delegation.models import DelegationRecord


TERMINAL_STATUSES = {"completed", "partial", "needs_input", "unsupported", "failed", "cancelled"}
SUCCESS_STATUSES = {"completed", "partial"}


def validate_acyclic(records: list[DelegationRecord]) -> None:
    ids = {record.id for record in records}
    if len(ids) != len(records):
        raise ValueError("委派 ID 不能重复。")
    graph: dict[str, list[str]] = {}
    for record in records:
        unknown = set(record.depends_on) - ids
        if unknown:
            raise ValueError(f"委派 {record.id} 引用了不存在的依赖：{sorted(unknown)}")
        if record.id in record.depends_on:
            raise ValueError(f"委派 {record.id} 不能依赖自身。")
        graph[record.id] = record.depends_on

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError("委派依赖图存在环。")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for record_id in graph:
        visit(record_id)


def ready_delegations(records: list[DelegationRecord]) -> list[DelegationRecord]:
    by_id = {record.id: record for record in records}
    return [
        record
        for record in records
        if record.status == "pending"
        and all(by_id[dependency].status in SUCCESS_STATUSES for dependency in record.depends_on)
    ]


def mark_blocked_delegations(records: list[DelegationRecord]) -> list[DelegationRecord]:
    by_id = {record.id: record for record in records}
    result: list[DelegationRecord] = []
    for record in records:
        if record.status == "pending" and any(
            by_id[dependency].status in TERMINAL_STATUSES - SUCCESS_STATUSES
            for dependency in record.depends_on
        ):
            result.append(record.model_copy(update={
                "status": "failed",
                "result": {"summary": "上游委派未成功，已停止执行。"},
            }))
        else:
            result.append(record)
    return result


def all_terminal(records: list[DelegationRecord]) -> bool:
    return bool(records) and all(record.status in TERMINAL_STATUSES for record in records)

