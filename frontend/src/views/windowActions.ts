import { currentMonitor, LogicalPosition, LogicalSize, Window } from "@tauri-apps/api/window";
import type { WindowView } from "../types/window";

export const FLOATING_CLOSED_SIZE = 132;
export const CONTEXT_MENU_WIDTH = 188;
export const CONTEXT_MENU_HEIGHT = 216;
export type OverlayShape = "quick" | "conversation" | "hud";

export const OVERLAY_SIZES: Record<OverlayShape, { width: number; height: number }> = {
  quick: { width: 430, height: 188 },
  conversation: { width: 430, height: 620 },
  hud: { width: 390, height: 96 }
};

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
  if (current.label === "overlay") {
    const restored = await restoreFloatingBall();
    if (!restored) {
      throw new Error("Unable to restore the floating ball; keeping overlay visible");
    }
  }
  await current.hide();
}

export async function restoreFloatingBall() {
  if (!isTauriRuntime()) {
    return true;
  }
  const floatingBall = await Window.getByLabel("floating-ball");
  if (!floatingBall) {
    return false;
  }
  const retryDelays = [0, 60, 160, 320];
  for (const delay of retryDelays) {
    if (delay) {
      await new Promise<void>((resolve) => window.setTimeout(resolve, delay));
    }
    await floatingBall.show().catch(() => undefined);
    if (await floatingBall.isVisible().catch(() => false)) {
      return true;
    }
  }
  return false;
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
    const monitor = await currentMonitor();
    const size = OVERLAY_SIZES.quick;
    await overlay.setSize(new LogicalSize(size.width, size.height));
    if (monitor) {
      const scaleFactor = monitor.scaleFactor;
      const workPosition = monitor.workArea.position;
      const workSize = monitor.workArea.size;
      const panelWidth = Math.round(size.width * scaleFactor);
      const panelHeight = Math.round(size.height * scaleFactor);
      const bottomMargin = Math.round(18 * scaleFactor);
      const nextX = workPosition.x + (workSize.width - panelWidth) / 2;
      const nextY = workPosition.y + workSize.height - panelHeight - bottomMargin;
      await overlay.setPosition(new LogicalPosition(nextX / scaleFactor, nextY / scaleFactor));
    }
    await overlay.show();
    await overlay.emitTo("overlay", "overlay-open-request");
    await overlay.setFocus();
    await floatingBall?.hide();
  } catch (error) {
    await restoreFloatingBall();
    await overlay.hide().catch(() => undefined);
    console.warn("Failed to show overlay window", error);
  }
}

export async function setOverlayWindowShape(shape: OverlayShape) {
  if (!isTauriRuntime()) {
    return;
  }
  const overlay = await Window.getByLabel("overlay");
  if (!overlay) {
    return;
  }
  const monitor = await currentMonitor();
  const nextSize = OVERLAY_SIZES[shape];
  if (!monitor) {
    await overlay.setSize(new LogicalSize(nextSize.width, nextSize.height));
    return;
  }

  const scaleFactor = monitor.scaleFactor;
  const workPosition = monitor.workArea.position;
  const workSize = monitor.workArea.size;
  const nextWidth = Math.round(nextSize.width * scaleFactor);
  const nextHeight = Math.round(nextSize.height * scaleFactor);
  const bottomMargin = Math.round(18 * scaleFactor);
  const nextX = workPosition.x + (workSize.width - nextWidth) / 2;
  const nextY = workPosition.y + workSize.height - nextHeight - bottomMargin;

  await overlay.setSize(new LogicalSize(nextSize.width, nextSize.height));
  await overlay.setPosition(new LogicalPosition(nextX / scaleFactor, nextY / scaleFactor));
}
