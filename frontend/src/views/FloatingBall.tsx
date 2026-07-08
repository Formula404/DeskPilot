import { MouseEvent as ReactMouseEvent, useEffect, useRef } from "react";
import { currentMonitor, LogicalPosition, LogicalSize, PhysicalPosition, Window } from "@tauri-apps/api/window";
import deskpilotWhiteIcon from "../assets/deskpilot-white.png";
import { useTaskStore } from "../store/taskStore";
import { gsap, useGSAP } from "../motion/register";
import { getMotionDuration, motion } from "../motion/constants";
import { useReducedMotion } from "../motion/useReducedMotion";
import { animatePress } from "../motion/animatePress";
import { getLatestTaskStatus } from "./taskStatus";
import {
  CONTEXT_MENU_HEIGHT,
  CONTEXT_MENU_WIDTH,
  FLOATING_CLOSED_SIZE,
  isTauriRuntime,
  showOverlayWindow
} from "./windowActions";
export function FloatingBallView() {
  const rootRef = useRef<HTMLElement | null>(null);
  const orbRef = useRef<HTMLButtonElement | null>(null);
  const idleTimelineRef = useRef<gsap.core.Timeline | null>(null);
  const statusTimelineRef = useRef<gsap.core.Timeline | null>(null);
  const dragStateRef = useRef<{ startX: number; startY: number; dragging: boolean } | null>(null);
  const reduceMotion = useReducedMotion();
  const { events, currentTaskId } = useTaskStore();
  const taskStatus = currentTaskId ? getLatestTaskStatus(events) : "idle";

  useEffect(() => {
    void initializeFloatingWindow();
  }, []);

  const { contextSafe } = useGSAP(() => {
    const orb = orbRef.current;
    const logo = rootRef.current?.querySelector("[data-motion='orb-logo']");
    const ring = rootRef.current?.querySelector("[data-motion='status-ring']");

    if (!orb || !logo || !ring) {
      return;
    }

    gsap.set(orb, { transformOrigin: "50% 50%", willChange: "transform, opacity" });
    gsap.set([logo, ring], { transformOrigin: "50% 50%", willChange: "transform, opacity" });

    const introTl = gsap.timeline({
      defaults: { ease: motion.ease.out },
      onComplete: () => {
        if (reduceMotion) {
          return;
        }
        idleTimelineRef.current?.kill();
        idleTimelineRef.current = gsap.timeline({ repeat: -1, yoyo: true, defaults: { ease: "sine.inOut" } })
          .to(ring, { autoAlpha: 0.72, scale: 1.025, duration: motion.duration.loop });
      }
    });

    introTl
      .fromTo(orb, { autoAlpha: 0, scale: 0.88, x: 12 }, { autoAlpha: 1, scale: 1, x: 0, duration: getMotionDuration(0.2, reduceMotion) })
      .from(logo, { autoAlpha: 0, scale: 0.82, duration: getMotionDuration(0.16, reduceMotion) }, "<0.04")
      .from(ring, { autoAlpha: 0, scale: 0.94, duration: getMotionDuration(0.18, reduceMotion) }, "<0.04");

    return () => {
      idleTimelineRef.current?.kill();
      statusTimelineRef.current?.kill();
    };
  }, { dependencies: [reduceMotion], scope: rootRef });

  useEffect(() => {
    const ring = rootRef.current?.querySelector("[data-motion='status-ring']");
    const dot = rootRef.current?.querySelector("[data-motion='status-dot']");
    const logo = rootRef.current?.querySelector("[data-motion='orb-logo']");
    if (!ring || !dot || !logo || reduceMotion) {
      return;
    }

    statusTimelineRef.current?.kill();
    gsap.set(dot, { autoAlpha: 0, scale: 0.6 });

    if (taskStatus === "idle") {
      return;
    }

    idleTimelineRef.current?.pause();
    if (taskStatus === "running") {
      statusTimelineRef.current = gsap.timeline({ repeat: -1 })
        .to(ring, { rotation: 360, duration: 1.15, ease: motion.ease.none })
        .to(logo, { scale: 1.04, duration: 0.45, ease: "sine.inOut", yoyo: true, repeat: 1 }, 0);
    } else if (taskStatus === "completed") {
      statusTimelineRef.current = gsap.timeline({
        onComplete: () => idleTimelineRef.current?.play()
      })
        .to(ring, { borderColor: "rgba(34, 197, 94, 0.82)", scale: 1.08, duration: 0.18, ease: motion.ease.out })
        .to(ring, { borderColor: "rgba(255, 255, 255, 0.16)", scale: 1, duration: 0.28, ease: motion.ease.out });
    } else {
      const color = taskStatus === "failed" ? "var(--color-danger)" : "#94a3b8";
      statusTimelineRef.current = gsap.timeline()
        .set(dot, { backgroundColor: color })
        .to(dot, { autoAlpha: 1, scale: 1, duration: 0.16, ease: motion.ease.out });
    }
  }, [reduceMotion, taskStatus]);

  async function initializeFloatingWindow() {
    if (!isTauriRuntime()) {
      return;
    }
    try {
      const current = Window.getCurrent();
      const monitor = await currentMonitor();
      await current.setSize(new LogicalSize(FLOATING_CLOSED_SIZE, FLOATING_CLOSED_SIZE));
      if (!monitor) {
        return;
      }
      const workAreaPosition = monitor.workArea.position.toLogical(monitor.scaleFactor);
      const workAreaSize = monitor.workArea.size.toLogical(monitor.scaleFactor);
      await current.setPosition(
        new LogicalPosition(
          workAreaPosition.x + workAreaSize.width - FLOATING_CLOSED_SIZE - 16,
          workAreaPosition.y + workAreaSize.height / 2 - FLOATING_CLOSED_SIZE / 2
        )
      );
    } catch (error) {
      console.warn("Failed to initialize floating window", error);
    }
  }

  const hoverOrb = contextSafe((hovered: boolean) => {
    if (hovered) {
      idleTimelineRef.current?.pause();
    } else {
      idleTimelineRef.current?.play();
    }
    gsap.to(orbRef.current, {
      scale: hovered ? 1.045 : 1,
      duration: hovered ? motion.duration.fast : motion.duration.base,
      ease: motion.ease.out
    });
  });

  const pressOrb = contextSafe(() => {
    animatePress(orbRef.current);
  });

  async function showContextMenu() {
    if (!isTauriRuntime()) {
      return;
    }
    try {
      const current = Window.getCurrent();
      const menu = await Window.getByLabel("context-menu");
      if (!menu) {
        return;
      }
      if (await menu.isVisible()) {
        await menu.hide();
        return;
      }
      const scaleFactor = await current.scaleFactor();
      const position = await current.outerPosition();
      const monitor = await currentMonitor();
      const menuWidth = Math.round(CONTEXT_MENU_WIDTH * scaleFactor);
      const menuHeight = Math.round(CONTEXT_MENU_HEIGHT * scaleFactor);
      let nextX = position.x - Math.round((CONTEXT_MENU_WIDTH + 10) * scaleFactor);
      let nextY = position.y + Math.round(14 * scaleFactor);
      if (monitor) {
        const minX = monitor.position.x;
        const minY = monitor.position.y;
        const maxX = minX + monitor.size.width - menuWidth;
        const maxY = minY + monitor.size.height - menuHeight;
        const rightSideX = position.x + Math.round((FLOATING_CLOSED_SIZE - 30) * scaleFactor);
        nextX = nextX < minX ? rightSideX : nextX;
        nextX = Math.min(Math.max(nextX, minX), maxX);
        nextY = Math.min(Math.max(nextY, minY), maxY);
      }
      await menu.setSize(new LogicalSize(CONTEXT_MENU_WIDTH, CONTEXT_MENU_HEIGHT));
      await menu.setPosition(new PhysicalPosition(nextX, nextY));
      await menu.show();
      await menu.setFocus();
    } catch (error) {
      console.warn("Failed to show context menu", error);
    }
  }

  async function openContextMenu(event: ReactMouseEvent<HTMLButtonElement>) {
    event.preventDefault();
    event.stopPropagation();
    await showContextMenu();
  }

  function startDragging(event: ReactMouseEvent<HTMLButtonElement>) {
    if (event.button !== 0 || !isTauriRuntime()) {
      return;
    }
    event.preventDefault();
    dragStateRef.current = {
      startX: event.screenX,
      startY: event.screenY,
      dragging: false
    };

    function cleanup() {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    }

    function onMouseMove(moveEvent: MouseEvent) {
      const state = dragStateRef.current;
      if (!state || state.dragging) {
        return;
      }
      const distance = Math.hypot(moveEvent.screenX - state.startX, moveEvent.screenY - state.startY);
      if (distance < 4) {
        return;
      }
      state.dragging = true;
      idleTimelineRef.current?.pause();
      gsap.to(orbRef.current, { autoAlpha: 0.82, scale: 0.96, duration: motion.duration.fast, ease: motion.ease.out });
      void Window.getByLabel("context-menu").then((menu) => menu?.hide());
      Window.getCurrent().startDragging().catch((error) => {
        console.warn("Failed to start dragging floating window", error);
      });
      cleanup();
    }

    function onMouseUp() {
      cleanup();
    }

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  }

  async function openOverlayOnClick() {
    if (dragStateRef.current?.dragging) {
      dragStateRef.current = null;
      return;
    }
    dragStateRef.current = null;
    await Window.getByLabel("context-menu").then((menu) => menu?.hide());
    await showOverlayWindow();
  }

  return (
    <main ref={rootRef} className="floating-stage" data-motion="floating-stage">
      <button
        ref={orbRef}
        className="floating-orb"
        data-motion="floating-orb"
        onClick={openOverlayOnClick}
        onContextMenu={openContextMenu}
        onMouseDown={startDragging}
        onPointerEnter={() => hoverOrb(true)}
        onPointerLeave={() => hoverOrb(false)}
        onPointerDown={pressOrb}
        onPointerUp={() => gsap.to(orbRef.current, { autoAlpha: 1, scale: 1, duration: motion.duration.fast, ease: motion.ease.out })}
        title="打开 DeskPilot，拖动可移动，右键打开菜单"
      >
        <img src={deskpilotWhiteIcon} alt="" className="orb-logo" data-motion="orb-logo" />
        <span className="status-ring" data-motion="status-ring" />
        <span className="status-dot" data-motion="status-dot" />
      </button>
    </main>
  );
}
