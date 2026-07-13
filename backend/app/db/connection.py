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
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
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

            CREATE TABLE IF NOT EXISTS schema_migrations (
              version INTEGER PRIMARY KEY,
              name TEXT NOT NULL,
              applied_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_sources (
              id TEXT PRIMARY KEY,
              source_type TEXT NOT NULL,
              canonical_uri TEXT,
              title TEXT,
              current_snapshot_id TEXT,
              sensitivity TEXT NOT NULL DEFAULT 'normal',
              status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(source_type, canonical_uri)
            );

            CREATE TABLE IF NOT EXISTS knowledge_snapshots (
              id TEXT PRIMARY KEY,
              source_id TEXT NOT NULL,
              content_sha256 TEXT NOT NULL,
              markdown_path TEXT NOT NULL UNIQUE,
              browser_context_id TEXT,
              captured_at TEXT NOT NULL,
              created_at TEXT NOT NULL,
              metadata_json TEXT NOT NULL DEFAULT '{}',
              FOREIGN KEY(source_id) REFERENCES knowledge_sources(id) ON DELETE CASCADE,
              UNIQUE(source_id, content_sha256)
            );

            CREATE TABLE IF NOT EXISTS knowledge_notes (
              id TEXT PRIMARY KEY,
              entity_type TEXT NOT NULL,
              title TEXT NOT NULL,
              normalized_title TEXT NOT NULL,
              markdown_path TEXT NOT NULL UNIQUE,
              status TEXT NOT NULL,
              review_state TEXT NOT NULL,
              sensitivity TEXT NOT NULL DEFAULT 'normal',
              content_sha256 TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_knowledge_notes_normalized_title
            ON knowledge_notes(normalized_title);

            CREATE TABLE IF NOT EXISTS knowledge_note_sources (
              note_id TEXT NOT NULL,
              source_id TEXT NOT NULL,
              snapshot_id TEXT,
              evidence_anchor TEXT NOT NULL DEFAULT '',
              PRIMARY KEY(note_id, source_id, evidence_anchor),
              FOREIGN KEY(note_id) REFERENCES knowledge_notes(id) ON DELETE CASCADE,
              FOREIGN KEY(source_id) REFERENCES knowledge_sources(id) ON DELETE CASCADE,
              FOREIGN KEY(snapshot_id) REFERENCES knowledge_snapshots(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_relations (
              id TEXT PRIMARY KEY,
              from_note_id TEXT NOT NULL,
              relation_type TEXT NOT NULL,
              to_note_id TEXT NOT NULL,
              source_id TEXT,
              confidence REAL,
              created_at TEXT NOT NULL,
              UNIQUE(from_note_id, relation_type, to_note_id),
              FOREIGN KEY(from_note_id) REFERENCES knowledge_notes(id) ON DELETE CASCADE,
              FOREIGN KEY(to_note_id) REFERENCES knowledge_notes(id) ON DELETE CASCADE,
              FOREIGN KEY(source_id) REFERENCES knowledge_sources(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_jobs (
              id TEXT PRIMARY KEY,
              task_id TEXT,
              job_type TEXT NOT NULL,
              target_id TEXT,
              status TEXT NOT NULL,
              attempt_count INTEGER NOT NULL DEFAULT 0,
              input_json TEXT,
              result_json TEXT,
              error_code TEXT,
              error_message TEXT,
              created_at TEXT NOT NULL,
              started_at TEXT,
              finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS knowledge_proposals (
              id TEXT PRIMARY KEY,
              job_id TEXT NOT NULL,
              operation TEXT NOT NULL,
              target_note_id TEXT,
              proposal_path TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              resolved_at TEXT,
              FOREIGN KEY(job_id) REFERENCES knowledge_jobs(id) ON DELETE CASCADE,
              FOREIGN KEY(target_note_id) REFERENCES knowledge_notes(id) ON DELETE SET NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
              object_id UNINDEXED,
              object_kind UNINDEXED,
              title,
              aliases,
              summary,
              body,
              tags,
              tokenize = 'unicode61'
            );
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
            VALUES (1, 'knowledge_base_initial', datetime('now'))
            """
        )
