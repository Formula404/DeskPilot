import type { TaskEvent } from "../types/api";
import type { OverlayMode, StepStatus } from "../types/window";

export function mapEventStatus(event: TaskEvent): StepStatus {
  if (event.type.includes("failed")) return "failed";
  if (event.type.includes("cancelled")) return "cancelled";
  if (event.type.includes("completed") || event.type.includes("finished")) return "success";
  if (event.type.includes("approval")) return "waiting";
  return "running";
}

export function isVisibleTaskStep(event: TaskEvent) {
  return event.type.startsWith("task.step.") || event.type.startsWith("approval.");
}

export function getLatestTaskStatus(events: TaskEvent[]): OverlayMode {
  if (events.some((event) => event.type === "task.failed")) return "failed";
  if (events.some((event) => event.type === "task.cancelled")) return "cancelled";
  if (events.some((event) => event.type === "task.completed")) return "completed";
  if (events.some((event) => event.type === "approval.required")) return "running";
  return events.length ? "running" : "idle";
}
