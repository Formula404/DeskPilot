from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from backend.app.core.paths import db_path, ensure_data_dirs


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    ensure_data_dirs()
    connection = sqlite3.connect(db_path())
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_runs (
              id TEXT PRIMARY KEY,
              user_message TEXT NOT NULL,
              intent TEXT,
              status TEXT NOT NULL,
              risk_level TEXT,
              result_summary TEXT,
              error_code TEXT,
              error_message TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_steps (
              id TEXT PRIMARY KEY,
              task_id TEXT NOT NULL,
              step_index INTEGER NOT NULL,
              type TEXT NOT NULL,
              name TEXT NOT NULL,
              input_json TEXT,
              output_json TEXT,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS approvals (
              id TEXT PRIMARY KEY,
              task_id TEXT NOT NULL,
              risk_level TEXT NOT NULL,
              summary TEXT NOT NULL,
              payload_json TEXT,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              resolved_at TEXT
            );

            CREATE TABLE IF NOT EXISTS browser_contexts (
              id TEXT PRIMARY KEY,
              tab_id TEXT,
              url TEXT NOT NULL,
              title TEXT,
              visible_text TEXT,
              dom_summary_json TEXT,
              captured_at TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_profiles (
              id TEXT PRIMARY KEY,
              app_key TEXT NOT NULL,
              display_name TEXT NOT NULL,
              process_name TEXT,
              exe_path TEXT,
              window_title_pattern TEXT,
              rpa_config_json TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_preferences (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              source TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memory_items (
              id TEXT PRIMARY KEY,
              kind TEXT NOT NULL,
              content TEXT NOT NULL,
              source_task_id TEXT,
              sensitivity TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(content, kind, content='memory_items', content_rowid='rowid');
            """
        )
