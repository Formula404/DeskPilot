import { useEffect } from "react";
import { getApplicationSettings } from "./api/client";
import { useWindowView } from "./hooks/useWindowView";
import { applyRuntimePreferences } from "./settings/runtimePreferences";
import { FloatingBallView } from "./views/FloatingBall";
import { ContextMenuView } from "./views/ContextMenu";
import { OverlayView } from "./views/Overlay";
import { SettingsView } from "./views/Settings";
import { KnowledgeWorkspaceView } from "./views/KnowledgeWorkspace";
import { PersonalInfoView } from "./views/PersonalInfo";

export function App() {
  const view = useWindowView();

  useEffect(() => {
    getApplicationSettings().then(applyRuntimePreferences).catch(() => {
      // The backend can still be starting while a Tauri window mounts.
    });
  }, []);

  if (view === "floating-ball") {
    return <FloatingBallView />;
  }

  if (view === "context-menu") {
    return <ContextMenuView />;
  }

  if (view === "settings") {
    return <SettingsView />;
  }

  if (view === "knowledge") {
    return <KnowledgeWorkspaceView />;
  }

  if (view === "personal-info") {
    return <PersonalInfoView />;
  }

  return <OverlayView />;
}
