import type {
  ChatResponse,
  KnowledgeLintResult,
  KnowledgeNoteDetail,
  KnowledgeNoteSummary,
  KnowledgeProfile,
  KnowledgeProposal,
  KnowledgeProposalDetail,
  KnowledgeSettings,
  KnowledgeSnapshotDetail,
  KnowledgeSourceDetail,
  KnowledgeSourceSummary,
  KnowledgeStatus,
  KnowledgeWebWatch,
  TaskEvent
} from "../types/api";

const API_BASE = "http://127.0.0.1:8765";

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    let message = `请求失败：${response.status}`;
    try {
      const payload = await response.json();
      message = payload?.detail?.message ?? payload?.detail ?? message;
    } catch {
      // Keep the HTTP status fallback when the response is not JSON.
    }
    throw new Error(String(message));
  }
  return response.json();
}

export async function createTask(message: string): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, source: "floating_window" })
  });
  if (!response.ok) {
    throw new Error(`Failed to create task: ${response.status}`);
  }
  return response.json();
}

export async function cancelTask(taskId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/tasks/${taskId}/cancel`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Failed to cancel task: ${response.status}`);
  }
}

export function openEventStream(
  onEvent: (event: TaskEvent) => void,
  onError?: () => void,
  onOpen?: () => void
): EventSource {
  const source = new EventSource(`${API_BASE}/events`);
  const eventTypes = [
    "task.created",
    "task.started",
    "task.plan.updated",
    "task.step.completed",
    "task.step.failed",
    "tool.started",
    "tool.finished",
    "tool.call.requested",
    "tool.observation.created",
    "approval.required",
    "task.completed",
    "task.failed",
    "task.cancelled"
  ];
  for (const type of eventTypes) {
    source.addEventListener(type, (message) => {
      onEvent(JSON.parse((message as MessageEvent).data));
    });
  }
  source.onopen = () => {
    onOpen?.();
  };
  source.onerror = () => {
    onError?.();
  };
  return source;
}

export function getKnowledgeStatus(): Promise<KnowledgeStatus> {
  return apiJson<KnowledgeStatus>("/knowledge/status");
}

export function getKnowledgeSettings(): Promise<KnowledgeSettings> {
  return apiJson<KnowledgeSettings>("/knowledge/settings");
}

export function updateKnowledgeSettings(settings: KnowledgeSettings): Promise<KnowledgeSettings> {
  const { active_profile_id: _activeProfileId, root_path: _rootPath, ...payload } = settings;
  return apiJson<KnowledgeSettings>("/knowledge/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export function ingestCurrentPage(): Promise<Record<string, unknown>> {
  return apiJson<Record<string, unknown>>("/knowledge/ingest/current-page", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}"
  });
}

export async function getKnowledgeProfiles(): Promise<{ items: KnowledgeProfile[]; active_profile_id: string }> {
  return apiJson("/knowledge/profiles");
}

export function createKnowledgeProfile(name: string, description = ""): Promise<KnowledgeProfile> {
  return apiJson("/knowledge/profiles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description })
  });
}

export function activateKnowledgeProfile(profileId: string): Promise<KnowledgeProfile> {
  return apiJson(`/knowledge/profiles/${profileId}/activate`, { method: "POST" });
}

export function deleteKnowledgeProfile(profileId: string): Promise<{ ok: boolean }> {
  return apiJson(`/knowledge/profiles/${profileId}`, { method: "DELETE" });
}

export function uploadKnowledgeFile(file: File): Promise<Record<string, unknown>> {
  const body = new FormData();
  body.append("file", file);
  body.append("compile", "true");
  return apiJson("/knowledge/ingest/upload", { method: "POST", body });
}

export async function getKnowledgeWatches(): Promise<KnowledgeWebWatch[]> {
  const result = await apiJson<{ items: KnowledgeWebWatch[] }>("/knowledge/watches");
  return result.items;
}

export function updateKnowledgeWatch(sourceId: string, enabled: boolean, intervalMinutes?: number): Promise<KnowledgeWebWatch> {
  return apiJson(`/knowledge/sources/${sourceId}/watch`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled, interval_minutes: intervalMinutes })
  });
}

export function checkKnowledgeSourceUpdate(sourceId: string): Promise<Record<string, unknown>> {
  return apiJson(`/knowledge/sources/${sourceId}/check-update`, { method: "POST" });
}

export function exportObsidianVault(): Promise<{ vault_path: string; notes: number; sources: number }> {
  return apiJson("/knowledge/obsidian/export", { method: "POST" });
}

export function chooseKnowledgeStorage(): Promise<{ path: string | null; cancelled: boolean }> {
  return apiJson("/knowledge/storage/choose", { method: "POST" });
}

export function changeKnowledgeStorage(path: string): Promise<{ root_path: string; migrated: boolean; rebuild: Record<string, number> }> {
  return apiJson("/knowledge/storage", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path })
  });
}

export function openKnowledgeStorage(): Promise<{ ok: boolean }> {
  return apiJson("/knowledge/storage/open", { method: "POST" });
}

export async function answerKnowledge(query: string): Promise<{ answer: string; results: KnowledgeNoteSummary[]; reading_level: string }> {
  const result = await apiJson<{ answer: string; results: Array<KnowledgeNoteSummary & { path?: string }>; reading_level: string }>("/knowledge/query", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query, mode: "answer" }) });
  return { ...result, results: result.results.map((item) => ({ ...item, markdown_path: item.markdown_path ?? item.path ?? "", updated_at: item.updated_at ?? "" })) };
}

export function promoteKnowledgeAnswer(title: string, answer: string, noteIds: string[]): Promise<KnowledgeNoteDetail> {
  return apiJson("/knowledge/promote", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title, answer, note_ids: noteIds }) });
}

export function semanticLintKnowledge(): Promise<Record<string, unknown>> {
  return apiJson("/knowledge/lint/semantic", { method: "POST" });
}

export function lintKnowledge(): Promise<KnowledgeLintResult> {
  return apiJson<KnowledgeLintResult>("/knowledge/lint", { method: "POST" });
}

export function rebuildKnowledgeIndex(): Promise<Record<string, unknown>> {
  return apiJson<Record<string, unknown>>("/knowledge/rebuild-index", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmed: true })
  });
}

export async function getKnowledgeProposals(): Promise<KnowledgeProposal[]> {
  const result = await apiJson<{ items: KnowledgeProposal[] }>("/knowledge/proposals");
  return result.items;
}

export function resolveKnowledgeProposal(proposalId: string, decision: "accept" | "reject"): Promise<Record<string, unknown>> {
  return apiJson<Record<string, unknown>>(`/knowledge/proposals/${proposalId}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision })
  });
}

export async function getKnowledgeNotes(params: {
  query?: string;
  entityType?: string;
  status?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<{ items: KnowledgeNoteSummary[]; total: number }> {
  const search = new URLSearchParams();
  if (params.query) search.set("query", params.query);
  if (params.entityType) search.set("entity_type", params.entityType);
  if (params.status) search.set("status", params.status);
  search.set("limit", String(params.limit ?? 50));
  search.set("offset", String(params.offset ?? 0));
  return apiJson<{ items: KnowledgeNoteSummary[]; total: number }>(`/knowledge/notes?${search.toString()}`);
}

export function getKnowledgeNote(noteId: string): Promise<KnowledgeNoteDetail> {
  return apiJson<KnowledgeNoteDetail>(`/knowledge/notes/${noteId}`);
}

export function updateKnowledgeNote(noteId: string, payload: { title: string; entity_type: string; summary: string; overview: string; details: string; tags: string[] }): Promise<KnowledgeNoteDetail> {
  return apiJson<KnowledgeNoteDetail>(`/knowledge/notes/${noteId}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}

export function deleteKnowledgeNote(noteId: string): Promise<{ id: string; title: string; deleted: boolean }> {
  return apiJson(`/knowledge/notes/${noteId}`, { method: "DELETE" });
}

export async function getKnowledgeSources(params: {
  query?: string;
  sourceType?: string;
  status?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<{ items: KnowledgeSourceSummary[]; total: number }> {
  const search = new URLSearchParams();
  if (params.query) search.set("query", params.query);
  if (params.sourceType) search.set("source_type", params.sourceType);
  if (params.status) search.set("status", params.status);
  search.set("limit", String(params.limit ?? 50));
  search.set("offset", String(params.offset ?? 0));
  return apiJson<{ items: KnowledgeSourceSummary[]; total: number }>(`/knowledge/sources?${search.toString()}`);
}

export function getKnowledgeSource(sourceId: string): Promise<KnowledgeSourceDetail> {
  return apiJson<KnowledgeSourceDetail>(`/knowledge/sources/${sourceId}`);
}

export function getKnowledgeSnapshot(snapshotId: string): Promise<KnowledgeSnapshotDetail> {
  return apiJson<KnowledgeSnapshotDetail>(`/knowledge/snapshots/${snapshotId}`);
}

export function getKnowledgeProposal(proposalId: string): Promise<KnowledgeProposalDetail> {
  return apiJson<KnowledgeProposalDetail>(`/knowledge/proposals/${proposalId}`);
}

export function compileKnowledgeSource(sourceId: string): Promise<Record<string, unknown>> {
  return apiJson<Record<string, unknown>>(`/knowledge/sources/${sourceId}/compile`, { method: "POST" });
}

export function refreshKnowledgeNote(noteId: string): Promise<{ note_id: string; pending: unknown[]; results: Array<Record<string, unknown>> }> {
  return apiJson(`/knowledge/notes/${noteId}/refresh`, { method: "POST" });
}
