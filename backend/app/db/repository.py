from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from backend.app.context.security import redact_secrets
from backend.app.db.connection import connect


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def create_task(
    user_message: str,
    status: str = "queued",
    *,
    session_id: str | None = None,
    turn_id: str | None = None,
    context_snapshot_id: str | None = None,
    parent_task_id: str | None = None,
) -> str:
    task_id = new_id()
    now = now_iso()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO task_runs
            (id, user_message, status, session_id, turn_id, context_snapshot_id,
             parent_task_id, context_version, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                task_id,
                user_message,
                status,
                session_id,
                turn_id,
                context_snapshot_id,
                parent_task_id,
                now,
                now,
            ),
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
                json.dumps(redact_secrets(input_data), ensure_ascii=False) if input_data is not None else None,
                json.dumps(redact_secrets(output_data), ensure_ascii=False) if output_data is not None else None,
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


def get_browser_context(context_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM browser_contexts WHERE id = ?", (context_id,)
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    data["dom_summary"] = json.loads(data.pop("dom_summary_json") or "[]")
    return data


def create_session(*, source: str = "floating_window", title: str | None = None) -> str:
    session_id = new_id()
    now = now_iso()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO sessions(id, title, source, status, created_at, updated_at)
            VALUES (?, ?, ?, 'active', ?, ?)
            """,
            (session_id, title, source, now, now),
        )
    return session_id


def get_session(session_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row) if row else None


def list_sessions(*, limit: int = 100) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def update_session(
    session_id: str,
    *,
    summary: str | None = None,
    summary_through_message_id: str | None = None,
    status: str | None = None,
) -> None:
    fields = ["updated_at = ?"]
    values: list[Any] = [now_iso()]
    for name, value in (
        ("summary", summary),
        ("summary_through_message_id", summary_through_message_id),
        ("status", status),
    ):
        if value is not None:
            fields.append(f"{name} = ?")
            values.append(value)
    values.append(session_id)
    with connect() as connection:
        connection.execute(f"UPDATE sessions SET {', '.join(fields)} WHERE id = ?", values)


def delete_session(session_id: str) -> bool:
    with connect() as connection:
        task_rows = connection.execute(
            "SELECT id FROM task_runs WHERE session_id = ?", (session_id,)
        ).fetchall()
        task_ids = [row["id"] for row in task_rows]
        for task_id in task_ids:
            connection.execute("DELETE FROM task_steps WHERE task_id = ?", (task_id,))
            connection.execute("DELETE FROM task_checkpoints WHERE task_id = ?", (task_id,))
            connection.execute("DELETE FROM context_usage WHERE task_id = ?", (task_id,))
            connection.execute("DELETE FROM approvals WHERE task_id = ?", (task_id,))
        connection.execute("DELETE FROM task_runs WHERE session_id = ?", (session_id,))
        # Keep deletion deterministic even if a legacy database was created
        # without the current ON DELETE CASCADE foreign keys.
        connection.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        connection.execute("DELETE FROM context_snapshots WHERE session_id = ?", (session_id,))
        cursor = connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    return cursor.rowcount > 0


def add_message(
    session_id: str,
    *,
    role: str,
    content: str,
    task_id: str | None = None,
    content_data: Any = None,
    sensitivity: str = "normal",
) -> str:
    message_id = new_id()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO messages
            (id, session_id, task_id, role, content, content_json, sensitivity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                session_id,
                task_id,
                role,
                content,
                json.dumps(content_data, ensure_ascii=False) if content_data is not None else None,
                sensitivity,
                now_iso(),
            ),
        )
    return message_id


def list_messages(session_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM (
              SELECT * FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?
            ) ORDER BY created_at ASC
            """,
            (session_id, limit),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["content_data"] = json.loads(item.pop("content_json") or "null")
        result.append(item)
    return result


def save_context_snapshot(
    *,
    session_id: str | None,
    source: str,
    window: dict[str, Any],
    browser: dict[str, Any],
    selection: dict[str, Any],
    attachments: list[dict[str, Any]],
    sensitivity: str,
    captured_at: str,
    expires_at: str | None,
) -> str:
    snapshot_id = new_id()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO context_snapshots
            (id, session_id, source, window_json, browser_json, selection_json,
             attachments_json, sensitivity, version, captured_at, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                snapshot_id,
                session_id,
                source,
                json.dumps(window, ensure_ascii=False),
                json.dumps(browser, ensure_ascii=False),
                json.dumps(selection, ensure_ascii=False),
                json.dumps(attachments, ensure_ascii=False),
                sensitivity,
                captured_at,
                expires_at,
                now_iso(),
            ),
        )
    return snapshot_id


def get_context_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM context_snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    for key in ("window", "browser", "selection", "attachments"):
        default = "[]" if key == "attachments" else "{}"
        data[key] = json.loads(data.pop(f"{key}_json") or default)
    return data


def delete_context_snapshot(snapshot_id: str) -> bool:
    with connect() as connection:
        cursor = connection.execute("DELETE FROM context_snapshots WHERE id = ?", (snapshot_id,))
    return cursor.rowcount > 0


def list_context_snapshots(*, limit: int = 100) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM context_snapshots ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        browser = json.loads(item.pop("browser_json") or "{}")
        item.pop("window_json", None)
        item.pop("selection_json", None)
        item.pop("attachments_json", None)
        item["browser"] = {
            key: browser.get(key) for key in ("tab_id", "url", "title") if browser.get(key) is not None
        }
        result.append(item)
    return result


def cleanup_expired_context(*, before: str | None = None) -> dict[str, int]:
    cutoff = before or now_iso()
    with connect() as connection:
        snapshots = connection.execute(
            "DELETE FROM context_snapshots WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (cutoff,),
        ).rowcount
        memories = connection.execute(
            "UPDATE memory_items SET status = 'expired' "
            "WHERE status = 'active' AND expires_at IS NOT NULL AND expires_at <= ?",
            (cutoff,),
        ).rowcount
    return {"context_snapshots": snapshots, "memory_items": memories}


def record_context_usage(task_id: str, node_name: str, blocks: list[dict[str, Any]]) -> None:
    with connect() as connection:
        for block in blocks:
            source = block.get("source") or {}
            connection.execute(
                """
                INSERT INTO context_usage
                (id, task_id, node_name, block_id, block_kind, source_type, source_id,
                 token_estimate, truncated, relevance_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id(),
                    task_id,
                    node_name,
                    block["id"],
                    block["kind"],
                    source.get("type"),
                    source.get("id"),
                    int(block.get("token_estimate") or 0),
                    int(bool(block.get("truncated"))),
                    block.get("relevance_score"),
                    now_iso(),
                ),
            )


def list_preferences(limit: int = 5) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM user_preferences ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def list_recent_artifacts(session_id: str, limit: int = 3) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT ts.task_id, ts.output_json, ts.created_at
            FROM task_steps ts
            JOIN task_runs tr ON tr.id = ts.task_id
            WHERE tr.session_id = ? AND ts.output_json IS NOT NULL
            ORDER BY ts.created_at DESC
            """,
            (session_id,),
        ).fetchall()
    artifacts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        output = json.loads(row["output_json"] or "{}")
        for item in output.get("artifacts") or []:
            path = str(item.get("path") or "") if isinstance(item, dict) else ""
            if not path or path in seen:
                continue
            seen.add(path)
            artifacts.append({**item, "task_id": row["task_id"], "created_at": row["created_at"]})
            if len(artifacts) >= limit:
                return artifacts
    return artifacts


def list_session_tasks(session_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM task_runs WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def save_task_checkpoint(task_id: str, node_name: str, state: dict[str, Any]) -> str:
    checkpoint_id = new_id()
    allowed = {
        key: state.get(key)
        for key in (
            "task_id",
            "session_id",
            "turn_id",
            "context_snapshot_id",
            "intent",
            "plan",
            "step_count",
            "artifacts",
            "approval_state",
            "final_response",
            "error",
        )
        if key in state
    }
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO task_checkpoints(id, task_id, node_name, state_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                checkpoint_id,
                task_id,
                node_name,
                json.dumps(redact_secrets(allowed), ensure_ascii=False),
                now_iso(),
            ),
        )
    return checkpoint_id


def get_latest_task_checkpoint(task_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM task_checkpoints WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["state"] = json.loads(result.pop("state_json") or "{}")
    return result


def list_recoverable_tasks() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM task_runs WHERE status IN ('queued', 'running') ORDER BY created_at"
        ).fetchall()
    return [dict(row) for row in rows]


def get_setting(key: str) -> str | None:
    with connect() as connection:
        row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else None


def set_setting(key: str, value: str) -> None:
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, now_iso()),
        )
