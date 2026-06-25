import type { ChatResponse, TaskEvent } from "../types/api";

const API_BASE = "http://127.0.0.1:8765";

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

export function openEventStream(onEvent: (event: TaskEvent) => void): EventSource {
  const source = new EventSource(`${API_BASE}/events`);
  const eventTypes = [
    "task.created",
    "task.started",
    "task.plan.updated",
    "tool.started",
    "tool.finished",
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
  return source;
}
