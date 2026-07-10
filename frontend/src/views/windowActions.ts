import { currentMonitor, LogicalPosition, LogicalSize, Window } from "@tauri-apps/api/window";
import type { WindowView } from "../types/window";
import { useWindowStore } from "../store/windowStore";

export const FLOATING_CLOSED_SIZE = 132;
export const CONTEXT_MENU_WIDTH = 188;
export const CONTEXT_MENU_HEIGHT = 178;

export function isTauriRuntime() {
  return "__TAURI_INTERNALS__" in window;
}

export async function showWindow(label: WindowView) {
  if (!isTauriRuntime()) {
    return;
  }
  const target = await Window.getByLabel(label);
  await target?.show();
  await target?.setFocus();
}

export async function hideCurrentWindow() {
  if (!isTauriRuntime()) {
    return;
  }
  const current = await Window.getCurrent();
  await current.hide();
  if (current.label === "overlay") {
    restoreFloatingBall();
  }
}

export function restoreFloatingBall() {
  if (!isTauriRuntime()) {
    return;
  }
  const restoreVersion = useWindowStore.getState().overlayLifecycleVersion;

  async function showIfOverlayClosed() {
    const [floatingBall, overlay] = await Promise.all([
      Window.getByLabel("floating-ball"),
      Window.getByLabel("overlay")
    ]);
    const overlayVisible = overlay ? await overlay.isVisible() : false;
    if (!floatingBall || overlayVisible || restoreVersion !== useWindowStore.getState().overlayLifecycleVersion) {
      return;
    }
    await floatingBall.show();
    const overlayReopened = overlay ? await overlay.isVisible() : false;
    if (overlayReopened || restoreVersion !== useWindowStore.getState().overlayLifecycleVersion) {
      await floatingBall.hide();
    }
  }

  void showIfOverlayClosed();
  window.setTimeout(() => void showIfOverlayClosed(), 120);
  window.setTimeout(() => void showIfOverlayClosed(), 360);
  window.setTimeout(() => void showIfOverlayClosed(), 900);
  window.setTimeout(() => void showIfOverlayClosed(), 1800);
}

export async function showOverlayWindow() {
  if (!isTauriRuntime()) {
    return;
  }
  const overlay = await Window.getByLabel("overlay");
  if (!overlay) {
    return;
  }
  const floatingBall = await Window.getByLabel("floating-ball");
  try {
    useWindowStore.getState().bumpOverlayLifecycleVersion();
    const monitor = await currentMonitor();
    if (monitor) {
      const position = monitor.position.toLogical(monitor.scaleFactor);
      const size = monitor.size.toLogical(monitor.scaleFactor);
      await overlay.setPosition(new LogicalPosition(position.x, position.y));
      await overlay.setSize(new LogicalSize(size.width, size.height));
    }
    await floatingBall?.hide();
    await overlay.show();
    await overlay.setFocus();
  } catch (error) {
    restoreFloatingBall();
    console.warn("Failed to show overlay window", error);
  }
}
