import type { FileText } from "lucide-react";

export type AppView = "floating-ball" | "overlay" | "settings" | "knowledge";
export type WindowView = AppView | "context-menu";
export type OverlayMode = "idle" | "creating" | "running" | "completed" | "failed" | "cancelled";
export type StepStatus = "success" | "running" | "failed" | "waiting" | "cancelled";

export interface SuggestedAction {
  id: string;
  label: string;
  prompt: string;
  icon: typeof FileText;
}
