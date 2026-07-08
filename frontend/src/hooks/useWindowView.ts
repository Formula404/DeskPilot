import { useEffect, useState } from "react";
import { Window } from "@tauri-apps/api/window";
import type { WindowView } from "../types/window";
import { isTauriRuntime } from "../views/windowActions";

export function useWindowView(): WindowView {
  const [view, setView] = useState<WindowView>("overlay");

  useEffect(() => {
    if (!isTauriRuntime()) {
      return;
    }
    try {
      const current = Window.getCurrent();
      const label = current.label as WindowView;
      if (label === "floating-ball" || label === "overlay" || label === "settings" || label === "context-menu") {
        setView(label);
      }
    } catch {
      setView("overlay");
    }
  }, []);

  return view;
}
