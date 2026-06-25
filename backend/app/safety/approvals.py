from __future__ import annotations


def create_approval_placeholder(task_id: str, summary: str) -> dict:
    return {"task_id": task_id, "summary": summary, "status": "pending"}
