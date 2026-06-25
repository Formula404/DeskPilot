from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from backend.app.db.connection import connect


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def create_task(user_message: str, status: str = "queued") -> str:
    task_id = new_id()
    now = now_iso()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO task_runs
            (id, user_message, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, user_message, status, now, now),
        )
    return task_id


def update_task(
    task_id: str,
    *,
    status: str | None = None,
    intent: str | None = None,
    result_summary: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    fields: list[str] = ["updated_at = ?"]
    values: list[Any] = [now_iso()]
    for name, value in [
        ("status", status),
        ("intent", intent),
        ("result_summary", result_summary),
        ("error_code", error_code),
        ("error_message", error_message),
    ]:
        if value is not None:
            fields.append(f"{name} = ?")
            values.append(value)
    values.append(task_id)
    with connect() as connection:
        connection.execute(
            f"UPDATE task_runs SET {', '.join(fields)} WHERE id = ?",
            values,
        )


def get_task(task_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM task_runs WHERE id = ?",
            (task_id,),
        ).fetchone()
    return dict(row) if row else None


def add_task_step(
    task_id: str,
    *,
    step_index: int,
    step_type: str,
    name: str,
    status: str,
    input_data: Any = None,
    output_data: Any = None,
) -> str:
    step_id = new_id()
    now = now_iso()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO task_steps
            (id, task_id, step_index, type, name, input_json, output_json, status, created_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                step_id,
                task_id,
                step_index,
                step_type,
                name,
                json.dumps(input_data, ensure_ascii=False) if input_data is not None else None,
                json.dumps(output_data, ensure_ascii=False) if output_data is not None else None,
                status,
                now,
                now if status in {"completed", "failed"} else None,
            ),
        )
    return step_id


def save_browser_context(
    *,
    tab_id: str | None,
    url: str,
    title: str | None,
    visible_text: str,
    dom_summary: Any,
    captured_at: str,
) -> str:
    context_id = new_id()
    now = now_iso()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO browser_contexts
            (id, tab_id, url, title, visible_text, dom_summary_json, captured_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                context_id,
                tab_id,
                url,
                title,
                visible_text,
                json.dumps(dom_summary, ensure_ascii=False),
                captured_at,
                now,
            ),
        )
    return context_id


def get_latest_browser_context() -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT * FROM browser_contexts
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    data["dom_summary"] = json.loads(data.pop("dom_summary_json") or "[]")
    return data
