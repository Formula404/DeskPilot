import type {
  ChatResponse,
  KnowledgeLintResult,
  KnowledgeProposal,
  KnowledgeSettings,
  KnowledgeStatus,
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
  return apiJson<KnowledgeSettings>("/knowledge/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings)
  });
}

export function ingestCurrentPage(): Promise<Record<string, unknown>> {
  return apiJson<Record<string, unknown>>("/knowledge/ingest/current-page", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}"
  });
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
