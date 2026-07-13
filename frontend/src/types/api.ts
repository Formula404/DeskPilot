export interface ChatResponse {
  task_id: string;
  status: string;
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
  enabled: boolean;
  auto_compile: boolean;
  review_updates: boolean;
  allow_private_remote: boolean;
  max_search_results: number;
  auto_create_notes: boolean;
  purpose: string;
  root_path: string;
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
