import { useEffect, useState } from "react";
import { PREFERENCES_CHANGED_EVENT } from "../settings/runtimePreferences";

function shouldReduceMotion(media: MediaQueryList): boolean {
  const mode = document.documentElement.dataset.motion;
  if (mode === "reduced") return true;
  if (mode === "full") return false;
  return media.matches;
}

export function useReducedMotion() {
  const [reduceMotion, setReduceMotion] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduceMotion(shouldReduceMotion(media));
    sync();

    function onChange(event: MediaQueryListEvent) {
      setReduceMotion(shouldReduceMotion(event.currentTarget as MediaQueryList));
    }

    media.addEventListener("change", onChange);
    window.addEventListener(PREFERENCES_CHANGED_EVENT, sync);
    return () => {
      media.removeEventListener("change", onChange);
      window.removeEventListener(PREFERENCES_CHANGED_EVENT, sync);
    };
  }, []);

  return reduceMotion;
}
