from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import Any

import httpx

from backend.app.db.connection import connect
from backend.app.db.repository import now_iso
from backend.app.knowledge.compiler import compile_source
from backend.app.knowledge.profiles import active_profile_id, use_profile
from backend.app.knowledge.repository import get_source
from backend.app.knowledge.settings import get_knowledge_settings
from backend.app.knowledge.source_service import ingest_content


class _ReadableHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.title = ""
        self._ignored = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored += 1
        if tag == "title":
            self._in_title = True
        if tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._ignored:
            self._ignored -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._ignored:
            return
        value = " ".join(data.split())
        if value:
            if self._in_title:
                self.title += value
            self.parts.append(value)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in " ".join(self.parts).splitlines()]
        return "\n\n".join(line for line in lines if line)


def set_watch(source_id: str, enabled: bool, interval_minutes: int | None = None) -> dict[str, Any]:
    settings = get_knowledge_settings()
    interval = interval_minutes or settings.web_update_interval_minutes
    next_check = (datetime.now(UTC) + timedelta(minutes=interval)).isoformat()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_web_watches
            (profile_id, source_id, enabled, interval_minutes, next_check_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id, source_id) DO UPDATE SET
              enabled=excluded.enabled, interval_minutes=excluded.interval_minutes,
              next_check_at=excluded.next_check_at, updated_at=excluded.updated_at
            """,
            (active_profile_id(), source_id, int(enabled), interval, next_check, now_iso()),
        )
    return get_watch(source_id) or {}


def get_watch(source_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM knowledge_web_watches WHERE profile_id=? AND source_id=?",
            (active_profile_id(), source_id),
        ).fetchone()
    return dict(row) if row else None


def list_watches() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT w.*, s.title, s.canonical_uri FROM knowledge_web_watches w
            JOIN knowledge_sources s ON s.id=w.source_id
            WHERE w.profile_id=? ORDER BY w.updated_at DESC
            """,
            (active_profile_id(),),
        ).fetchall()
    return [dict(row) for row in rows]


async def check_web_source(source_id: str) -> dict[str, Any]:
    source = get_source(source_id)
    if not source or source.get("source_type") != "web" or not source.get("canonical_uri"):
        raise ValueError("该来源不是可检查的网页来源。")
    watch = get_watch(source_id)
    interval = int((watch or {}).get("interval_minutes") or get_knowledge_settings().web_update_interval_minutes)
    # A manual check also establishes a watch. Existing watches retain their
    # explicit state, while a newly created row must be schedulable.
    watch_enabled = int(bool(watch.get("enabled"))) if watch else 1
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20, headers={"User-Agent": "DeskPilot/0.1"}) as client:
            response = await client.get(str(source["canonical_uri"]))
            response.raise_for_status()
        parser = _ReadableHTML()
        parser.feed(response.text)
        content = parser.text()
        result = ingest_content(
            source_type="web",
            title=parser.title.strip() or str(source.get("title") or source["canonical_uri"]),
            content=content,
            canonical_uri=str(source["canonical_uri"]),
            sensitivity=str(source.get("sensitivity") or "normal"),
            capture_method="scheduled_web_check",
            metadata={"http_status": response.status_code, "final_url": str(response.url)},
        )
        compilation = None
        if result["status"] == "updated" and get_knowledge_settings().auto_compile:
            compilation = await compile_source(source_id)
        status = "changed" if result["status"] == "updated" else "unchanged"
        error = None
    except Exception as exc:
        result = {"source_id": source_id}
        compilation = None
        status = "failed"
        error = str(exc)
    next_check = (datetime.now(UTC) + timedelta(minutes=interval)).isoformat()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO knowledge_web_watches
            (profile_id, source_id, enabled, interval_minutes, last_checked_at, next_check_at, last_status, last_error, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id, source_id) DO UPDATE SET
              last_checked_at=excluded.last_checked_at, next_check_at=excluded.next_check_at,
              last_changed_at=CASE WHEN excluded.last_status='changed' THEN excluded.last_checked_at ELSE knowledge_web_watches.last_changed_at END,
              last_status=excluded.last_status, last_error=excluded.last_error, updated_at=excluded.updated_at
            """,
            (active_profile_id(), source_id, watch_enabled, interval, now_iso(), next_check, status, error, now_iso()),
        )
    return {**result, "check_status": status, "error": error, "compilation": compilation, "next_check_at": next_check}


async def scheduler_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        now = now_iso()
        with connect() as connection:
            rows = connection.execute(
                """
                SELECT profile_id, source_id FROM knowledge_web_watches
                WHERE enabled=1 AND (next_check_at IS NULL OR next_check_at <= ?)
                LIMIT 20
                """,
                (now,),
            ).fetchall()
        for row in rows:
            with use_profile(str(row["profile_id"])):
                if get_knowledge_settings().web_update_enabled:
                    await check_web_source(str(row["source_id"]))
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except TimeoutError:
            continue
