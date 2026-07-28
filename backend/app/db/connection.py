from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Condition, RLock

from backend.app.core.paths import db_path, ensure_data_dirs


_database_gate = Condition(RLock())
_active_connections = 0
_exclusive_access = False


@contextmanager
def exclusive_database_access() -> Iterator[None]:
    """Block new app connections and wait until existing ones are closed.

    Database restore uses this process-local barrier before copying pages into the
    live SQLite database. It avoids replacing a file that is still referenced by
    another request (notably unsafe on Windows and with stale inodes on POSIX).
    """
    global _exclusive_access
    with _database_gate:
        while _exclusive_access:
            _database_gate.wait()
        _exclusive_access = True
        while _active_connections:
            _database_gate.wait()
    try:
        yield
    finally:
        with _database_gate:
            _exclusive_access = False
            _database_gate.notify_all()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    global _active_connections
    ensure_data_dirs()
    with _database_gate:
        while _exclusive_access:
            _database_gate.wait()
        _active_connections += 1
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(db_path(), timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        yield connection
        connection.commit()
    finally:
        if connection is not None:
            connection.close()
        with _database_gate:
            _active_connections -= 1
            _database_gate.notify_all()


def init_db() -> None:
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY,
              title TEXT,
              summary TEXT NOT NULL DEFAULT '',
              summary_through_message_id TEXT,
              status TEXT NOT NULL DEFAULT 'active',
              source TEXT NOT NULL DEFAULT 'floating_window',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              archived_at TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
              id TEXT PRIMARY KEY,
              session_id TEXT NOT NULL,
              task_id TEXT,
              role TEXT NOT NULL,
              content TEXT NOT NULL,
              content_json TEXT,
              sensitivity TEXT NOT NULL DEFAULT 'normal',
              created_at TEXT NOT NULL,
              FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session_created
            ON messages(session_id, created_at);

            CREATE TABLE IF NOT EXISTS context_snapshots (
              id TEXT PRIMARY KEY,
              session_id TEXT,
              source TEXT NOT NULL,
              window_json TEXT NOT NULL DEFAULT '{}',
              browser_json TEXT NOT NULL DEFAULT '{}',
              selection_json TEXT NOT NULL DEFAULT '{}',
              attachments_json TEXT NOT NULL DEFAULT '[]',
              sensitivity TEXT NOT NULL DEFAULT 'normal',
              version INTEGER NOT NULL DEFAULT 1,
              captured_at TEXT NOT NULL,
              expires_at TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
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

            CREATE TABLE IF NOT EXISTS personal_info_fields (
              id TEXT PRIMARY KEY,
              category TEXT NOT NULL,
              field_key TEXT NOT NULL UNIQUE,
              label TEXT NOT NULL,
              value TEXT NOT NULL,
              aliases_json TEXT NOT NULL DEFAULT '[]',
              source_type TEXT NOT NULL,
              source_ref TEXT,
              confidence REAL NOT NULL DEFAULT 1.0,
              status TEXT NOT NULL DEFAULT 'confirmed',
              sensitivity TEXT NOT NULL DEFAULT 'personal',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_personal_info_category_status
            ON personal_info_fields(category, status, updated_at);

            CREATE TABLE IF NOT EXISTS form_templates (
              id TEXT PRIMARY KEY,
              origin TEXT NOT NULL,
              path_pattern TEXT NOT NULL,
              title TEXT NOT NULL DEFAULT '',
              signature TEXT NOT NULL UNIQUE,
              fields_json TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS personal_info_records (
              id TEXT PRIMARY KEY,
              category TEXT NOT NULL,
              record_type TEXT NOT NULL,
              label TEXT NOT NULL,
              fingerprint TEXT NOT NULL UNIQUE,
              source_type TEXT NOT NULL,
              source_ref TEXT,
              confidence REAL NOT NULL DEFAULT 1.0,
              status TEXT NOT NULL DEFAULT 'confirmed',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_personal_info_records_category
            ON personal_info_records(category, updated_at);

            CREATE TABLE IF NOT EXISTS personal_info_record_fields (
              id TEXT PRIMARY KEY,
              record_id TEXT NOT NULL,
              field_key TEXT NOT NULL,
              label TEXT NOT NULL,
              value TEXT NOT NULL,
              aliases_json TEXT NOT NULL DEFAULT '[]',
              confidence REAL NOT NULL DEFAULT 1.0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(record_id, field_key),
              FOREIGN KEY(record_id) REFERENCES personal_info_records(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS form_fill_memories (
              id TEXT PRIMARY KEY,
              origin TEXT NOT NULL,
              path_pattern TEXT NOT NULL,
              field_signature TEXT NOT NULL,
              field_label TEXT NOT NULL DEFAULT '',
              section_key TEXT NOT NULL DEFAULT '',
              field_key TEXT,
              action TEXT NOT NULL DEFAULT 'map',
              source_field_id TEXT,
              source_record_id TEXT,
              override_value TEXT,
              priority INTEGER NOT NULL DEFAULT 100,
              use_count INTEGER NOT NULL DEFAULT 0,
              last_used_at TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(origin, path_pattern, field_signature)
            );

            CREATE INDEX IF NOT EXISTS idx_form_fill_memories_scope
            ON form_fill_memories(origin, path_pattern, updated_at);

            CREATE TABLE IF NOT EXISTS form_fill_sessions (
              id TEXT PRIMARY KEY,
              origin TEXT NOT NULL,
              path_pattern TEXT NOT NULL,
              url TEXT NOT NULL,
              title TEXT NOT NULL DEFAULT '',
              tab_id TEXT,
              document_id TEXT,
              plan_json TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              expires_at TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_form_fill_sessions_expiry
            ON form_fill_sessions(status, expires_at);

            CREATE TABLE IF NOT EXISTS context_usage (
              id TEXT PRIMARY KEY,
              task_id TEXT NOT NULL,
              node_name TEXT NOT NULL,
              block_id TEXT NOT NULL,
              block_kind TEXT NOT NULL,
              source_type TEXT,
              source_id TEXT,
              token_estimate INTEGER NOT NULL DEFAULT 0,
              truncated INTEGER NOT NULL DEFAULT 0,
              relevance_score REAL,
              created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_context_usage_task
            ON context_usage(task_id, node_name, created_at);

            CREATE TABLE IF NOT EXISTS task_checkpoints (
              id TEXT PRIMARY KEY,
              task_id TEXT NOT NULL,
              node_name TEXT NOT NULL,
              state_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_task_checkpoints_task_created
            ON task_checkpoints(task_id, created_at);

            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(content, kind, content='memory_items', content_rowid='rowid');

            CREATE TRIGGER IF NOT EXISTS memory_items_ai AFTER INSERT ON memory_items BEGIN
              INSERT INTO memory_fts(rowid, content, kind) VALUES (new.rowid, new.content, new.kind);
            END;
            CREATE TRIGGER IF NOT EXISTS memory_items_ad AFTER DELETE ON memory_items BEGIN
              INSERT INTO memory_fts(memory_fts, rowid, content, kind)
              VALUES ('delete', old.rowid, old.content, old.kind);
            END;
            CREATE TRIGGER IF NOT EXISTS memory_items_au AFTER UPDATE ON memory_items BEGIN
              INSERT INTO memory_fts(memory_fts, rowid, content, kind)
              VALUES ('delete', old.rowid, old.content, old.kind);
              INSERT INTO memory_fts(rowid, content, kind) VALUES (new.rowid, new.content, new.kind);
            END;

            CREATE TABLE IF NOT EXISTS schema_migrations (
              version INTEGER PRIMARY KEY,
              name TEXT NOT NULL,
              applied_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_profiles (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              description TEXT NOT NULL DEFAULT '',
              is_default INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_profile_sources (
              profile_id TEXT NOT NULL,
              source_id TEXT NOT NULL,
              PRIMARY KEY(profile_id, source_id),
              FOREIGN KEY(profile_id) REFERENCES knowledge_profiles(id) ON DELETE CASCADE,
              FOREIGN KEY(source_id) REFERENCES knowledge_sources(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS knowledge_profile_notes (
              profile_id TEXT NOT NULL,
              note_id TEXT NOT NULL,
              PRIMARY KEY(profile_id, note_id),
              FOREIGN KEY(profile_id) REFERENCES knowledge_profiles(id) ON DELETE CASCADE,
              FOREIGN KEY(note_id) REFERENCES knowledge_notes(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS knowledge_web_watches (
              profile_id TEXT NOT NULL,
              source_id TEXT NOT NULL,
              enabled INTEGER NOT NULL DEFAULT 1,
              interval_minutes INTEGER NOT NULL DEFAULT 1440,
              last_checked_at TEXT,
              last_changed_at TEXT,
              next_check_at TEXT,
              last_status TEXT,
              last_error TEXT,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(profile_id, source_id),
              FOREIGN KEY(profile_id) REFERENCES knowledge_profiles(id) ON DELETE CASCADE,
              FOREIGN KEY(source_id) REFERENCES knowledge_sources(id) ON DELETE CASCADE
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

            CREATE TABLE IF NOT EXISTS knowledge_job_events (
              id TEXT PRIMARY KEY,
              job_id TEXT NOT NULL,
              event_type TEXT NOT NULL,
              progress INTEGER NOT NULL,
              message TEXT NOT NULL,
              payload_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL,
              FOREIGN KEY(job_id) REFERENCES knowledge_jobs(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS knowledge_locks (
              resource_key TEXT PRIMARY KEY,
              owner_id TEXT NOT NULL,
              acquired_at TEXT NOT NULL,
              expires_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_proposals (
              id TEXT PRIMARY KEY,
              job_id TEXT NOT NULL,
              operation TEXT NOT NULL,
              target_note_id TEXT,
              proposal_path TEXT NOT NULL,
              base_note_sha256 TEXT,
              base_snapshot_id TEXT,
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
        task_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(task_runs)").fetchall()
        }
        for name, definition in {
            "session_id": "TEXT",
            "turn_id": "TEXT",
            "context_snapshot_id": "TEXT",
            "parent_task_id": "TEXT",
            "context_version": "INTEGER NOT NULL DEFAULT 1",
            "manager_model": "TEXT",
            "manager_prompt_version": "TEXT",
            "intent_schema_version": "INTEGER",
            "intent_understanding_json": "TEXT",
            "manager_latency_ms": "INTEGER",
            "manager_fallback_reason": "TEXT",
            "delegation_count": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if name not in task_columns:
                connection.execute(f"ALTER TABLE task_runs ADD COLUMN {name} {definition}")
        memory_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(memory_items)").fetchall()
        }
        for name, definition in {
            "key": "TEXT",
            "value_json": "TEXT",
            "confidence": "REAL NOT NULL DEFAULT 1.0",
            "source_type": "TEXT",
            "expires_at": "TEXT",
            "last_used_at": "TEXT",
            "use_count": "INTEGER NOT NULL DEFAULT 0",
            "status": "TEXT NOT NULL DEFAULT 'active'",
        }.items():
            if name not in memory_columns:
                connection.execute(f"ALTER TABLE memory_items ADD COLUMN {name} {definition}")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_runs_session_created ON task_runs(session_id, created_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_context_snapshots_session_created "
            "ON context_snapshots(session_id, created_at)"
        )
        watch_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(knowledge_web_watches)").fetchall()
        }
        if "last_changed_at" not in watch_columns:
            connection.execute("ALTER TABLE knowledge_web_watches ADD COLUMN last_changed_at TEXT")
        proposal_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(knowledge_proposals)").fetchall()
        }
        if "base_note_sha256" not in proposal_columns:
            connection.execute("ALTER TABLE knowledge_proposals ADD COLUMN base_note_sha256 TEXT")
        if "base_snapshot_id" not in proposal_columns:
            connection.execute("ALTER TABLE knowledge_proposals ADD COLUMN base_snapshot_id TEXT")
        for table in ("knowledge_notes", "knowledge_sources"):
            columns = {
                row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if "deleted_at" not in columns:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN deleted_at TEXT")
            if "previous_status" not in columns:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN previous_status TEXT")
        job_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(knowledge_jobs)").fetchall()
        }
        for name, definition in {
            "progress": "INTEGER NOT NULL DEFAULT 0",
            "cancel_requested": "INTEGER NOT NULL DEFAULT 0",
            "max_attempts": "INTEGER NOT NULL DEFAULT 3",
            "profile_id": "TEXT",
            "updated_at": "TEXT",
        }.items():
            if name not in job_columns:
                connection.execute(f"ALTER TABLE knowledge_jobs ADD COLUMN {name} {definition}")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_knowledge_jobs_status ON knowledge_jobs(status, created_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_knowledge_proposals_target_status "
            "ON knowledge_proposals(target_note_id, status)"
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
            VALUES (1, 'knowledge_base_initial', datetime('now'))
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO knowledge_profiles
            (id, name, description, is_default, created_at, updated_at)
            VALUES ('profile_default', '默认知识库', 'DeskPilot 默认知识空间', 1, datetime('now'), datetime('now'))
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO knowledge_profile_sources(profile_id, source_id)
            SELECT 'profile_default', id FROM knowledge_sources
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO knowledge_profile_notes(profile_id, note_id)
            SELECT 'profile_default', id FROM knowledge_notes
            """
        )
