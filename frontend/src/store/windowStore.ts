import { create } from "zustand";

interface WindowState {
  overlayLifecycleVersion: number;
  bumpOverlayLifecycleVersion: () => number;
}

export const useWindowStore = create<WindowState>((set, get) => ({
  overlayLifecycleVersion: 0,
  bumpOverlayLifecycleVersion: () => {
    const nextVersion = get().overlayLifecycleVersion + 1;
    set({ overlayLifecycleVersion: nextVersion });
    return nextVersion;
  }
}));

