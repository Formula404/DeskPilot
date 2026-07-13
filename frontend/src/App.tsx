import { useWindowView } from "./hooks/useWindowView";
import { FloatingBallView } from "./views/FloatingBall";
import { ContextMenuView } from "./views/ContextMenu";
import { OverlayView } from "./views/Overlay";
import { SettingsView } from "./views/Settings";
import { KnowledgeWorkspaceView } from "./views/KnowledgeWorkspace";

export function App() {
  const view = useWindowView();

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

  return <OverlayView />;
}
