export interface ChatResponse {
  task_id: string;
  status: string;
  session_id: string;
  context_snapshot_id: string | null;
}

export interface SessionResponse {
  session_id: string;
  status: string;
}

export interface ContextSnapshotResponse {
  context_snapshot_id: string;
  captured_at: string;
  expires_at: string | null;
  available: { window: boolean; browser: boolean; selection: boolean };
  degraded_reasons: string[];
}

export interface ContextDataOverview {
  counts: { sessions: number; snapshots: number };
  sessions: Array<{ id: string; title: string | null; status: string; updated_at: string }>;
  snapshots: Array<{
    id: string;
    session_id: string | null;
    source: string;
    browser: { tab_id?: string; url?: string; title?: string };
    sensitivity: string;
    captured_at: string;
    expires_at: string | null;
  }>;
}

export interface MemoryOverview {
  items: Array<{
    id: string;
    kind: string;
    content: string;
    sensitivity: string;
    status: string;
    updated_at: string;
  }>;
}

export interface TaskArtifact {
  type: string;
  path: string;
}

export interface ApplicationSettings {
  schema_version: number;
  ai: {
    provider: "openai_compatible";
    base_url: string;
    model: string;
    temperature: number;
    request_timeout_seconds: number;
    api_key_configured: boolean;
    api_key_hint: string | null;
  };
  general: {
    response_language: "zh-CN" | "en";
    motion_mode: "system" | "reduced" | "full";
  };
  manager: {
    enabled: boolean;
    model: string | null;
    timeout_seconds: number;
    max_delegations: number;
    max_manager_turns: number;
    structured_output_mode: "auto" | "native" | "json";
    clarification_confidence_threshold: number;
  };
  specialists: Record<"web" | "knowledge" | "file" | "desktop", {
    model: string | null;
    timeout_seconds: number;
    max_tool_steps: number;
  }>;
}

export interface ApplicationSettingsUpdate {
  schema_version: number;
  ai: Omit<ApplicationSettings["ai"], "api_key_configured" | "api_key_hint"> & {
    api_key: string | null;
  };
  general: ApplicationSettings["general"];
  manager: ApplicationSettings["manager"];
  specialists: ApplicationSettings["specialists"];
}

export interface TaskEvent {
  event_id: string;
  task_id: string | null;
  type: string;
  message: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface KnowledgeStatus {
  active_profile_id: string;
  sources: number;
  snapshots: number;
  notes: number;
  stale_notes: number;
  pending_proposals: number;
  enabled: boolean;
  browser_connected: boolean;
  root_path: string;
}

export interface KnowledgeSettings {
  active_profile_id: string;
  enabled: boolean;
  auto_compile: boolean;
  review_updates: boolean;
  allow_private_remote: boolean;
  max_search_results: number;
  auto_create_notes: boolean;
  web_update_enabled: boolean;
  web_update_interval_minutes: number;
  auto_watch_web_sources: boolean;
  obsidian_enabled: boolean;
  obsidian_include_sources: boolean;
  purpose: string;
  root_path: string;
}

export interface KnowledgeProfile {
  id: string;
  name: string;
  description: string;
  is_default: number;
  is_active: boolean;
  source_count: number;
  note_count: number;
}

export interface KnowledgeWebWatch {
  source_id: string;
  profile_id: string;
  enabled: number;
  interval_minutes: number;
  last_checked_at: string | null;
  last_changed_at: string | null;
  next_check_at: string | null;
  last_status: string | null;
  last_error: string | null;
  title: string;
  canonical_uri: string;
}

export interface KnowledgeLintResult {
  ok: boolean;
  summary: { errors: number; warnings: number; info: number };
  issues: Array<{ level: string; code: string; message: string; path?: string }>;
  scanned: { sources: number; notes: number };
}

export interface KnowledgeProposal {
  id: string;
  operation: string;
  target_note_id: string | null;
  target_title: string | null;
  created_at: string;
  status: string;
}

export interface KnowledgeNoteSummary {
  id: string;
  entity_type: string;
  title: string;
  status: string;
  review_state: string;
  sensitivity: string;
  markdown_path: string;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeEvidenceRef {
  note_id: string;
  source_id: string;
  snapshot_id: string | null;
  evidence_anchor: string;
  source_title: string;
  canonical_uri: string | null;
  sensitivity: string;
}

export interface KnowledgeRelation {
  id: string;
  relation_type: string;
  to_note_id: string;
  target_title: string;
  confidence: number | null;
}

export interface KnowledgeNoteDetail extends KnowledgeNoteSummary {
  frontmatter: {
    aliases: string[];
    tags: string[];
    source_ids: string[];
    manual_sections: string[];
    generated_by: string;
  };
  sections: Record<string, string>;
  content: string;
  sources: KnowledgeEvidenceRef[];
  relations: KnowledgeRelation[];
}

export interface KnowledgeSourceSummary {
  id: string;
  source_type: string;
  canonical_uri: string | null;
  title: string;
  current_snapshot_id: string | null;
  sensitivity: string;
  status: string;
  created_at: string;
  updated_at: string;
  snapshot_count: number;
  note_count: number;
}

export interface KnowledgeSnapshotSummary {
  id: string;
  source_id: string;
  content_sha256: string;
  markdown_path: string;
  captured_at: string;
  created_at: string;
}

export interface KnowledgeSourceDetail extends KnowledgeSourceSummary {
  snapshots: KnowledgeSnapshotSummary[];
  watch: KnowledgeWebWatch | null;
}

export interface KnowledgeSnapshotDetail extends KnowledgeSnapshotSummary {
  frontmatter: Record<string, unknown>;
  sections: Record<string, string>;
  content: string;
  metadata: Record<string, unknown>;
}

export interface KnowledgeProposalDetail extends KnowledgeProposal {
  payload: {
    source_id: string;
    snapshot_id: string;
    operation: {
      operation: string;
      title: string;
      entity_type: string;
      summary: string;
      overview: string;
      details_markdown: string;
      aliases: string[];
      tags: string[];
    };
  } | null;
  target_note: KnowledgeNoteDetail | null;
  diff: {
    fields: Array<{ field: string; before: unknown; after: unknown; changed: boolean }>;
    unified_diff: string[];
    evidence: { added: string[][]; removed: string[][] };
    relations: { added: string[][]; removed: string[][] };
    base: { expected_note_sha256: string | null; current_note_sha256: string | null; matches: boolean; snapshot_id: string | null };
    changed_fields: string[];
  };
}

export type KnowledgeQueryMode = "answer" | "compare" | "timeline" | "explore";

export interface KnowledgeQueryResult {
  mode?: KnowledgeQueryMode;
  answer: string;
  results: KnowledgeNoteSummary[];
  reading_level: string;
  comparison?: Record<string, unknown>;
  timeline?: Array<Record<string, unknown>>;
  graph?: Record<string, unknown>;
}

export interface KnowledgeJob {
  id: string;
  job_type: string;
  target_id: string | null;
  status: string;
  progress: number;
  attempt_count: number;
  max_attempts: number;
  error_code: string | null;
  error_message: string | null;
}
