import type { ApplicationSettings } from "../types/api";

export const PREFERENCES_CHANGED_EVENT = "deskpilot:preferences-changed";

export function applyRuntimePreferences(settings: ApplicationSettings): void {
  document.documentElement.dataset.motion = settings.general.motion_mode;
  document.documentElement.lang = settings.general.response_language;
  window.dispatchEvent(new CustomEvent(PREFERENCES_CHANGED_EVENT));
}
