import { MouseEvent as ReactMouseEvent, useCallback, useRef } from "react";
import { BookOpen, History, Power, Settings, User } from "lucide-react";
import { gsap, useGSAP } from "../motion/register";
import { getMotionDuration, motion } from "../motion/constants";
import { useReducedMotion } from "../motion/useReducedMotion";
import { useWindowLifecycle } from "../hooks/useWindowLifecycle";
import { hideCurrentWindow, showWindow } from "./windowActions";
export function ContextMenuView() {
  const rootRef = useRef<HTMLElement | null>(null);
  const afterCloseRef = useRef<(() => Promise<void>) | undefined>(undefined);
  const reduceMotion = useReducedMotion();

  const playMenuOpenMotion = useCallback(() => {
    const menu = rootRef.current?.querySelector("[data-motion='orb-menu']");
    const items = rootRef.current?.querySelectorAll("[data-motion='orb-menu-item']");
    const divider = rootRef.current?.querySelector("[data-motion='orb-menu-divider']");
    if (!menu || !items?.length) {
      return;
    }

    gsap.killTweensOf([menu, divider, ...Array.from(items)]);
    gsap.set([menu, divider, ...Array.from(items)], { autoAlpha: 1, clearProps: "visibility" });
    gsap.timeline({ defaults: { ease: motion.ease.out } })
      .fromTo(menu, {
        scale: 0.94,
        y: 6,
        transformOrigin: "right 28px"
      }, {
        scale: 1,
        y: 0,
        duration: getMotionDuration(0.16, reduceMotion)
      })
      .from(items, {
        x: -4,
        duration: getMotionDuration(0.14, reduceMotion),
        stagger: reduceMotion ? 0 : motion.stagger.tight
      }, "<0.04")
      .from(divider ?? [], {
        scaleX: 0,
        transformOrigin: "left center",
        duration: getMotionDuration(0.12, reduceMotion)
      }, "<0.06");
  }, [reduceMotion]);

  const resetMenuMotionTargets = useCallback(() => {
    const menu = rootRef.current?.querySelector("[data-motion='orb-menu']");
    const items = rootRef.current?.querySelectorAll("[data-motion='orb-menu-item']");
    const divider = rootRef.current?.querySelector("[data-motion='orb-menu-divider']");
    const targets = [
      ...(menu ? [menu] : []),
      ...(divider ? [divider] : []),
      ...Array.from(items ?? [])
    ];
    gsap.killTweensOf(targets);
    gsap.set(targets, { autoAlpha: 1, x: 0, y: 0, scale: 1, rotation: 0, clearProps: "visibility" });
  }, []);

  useGSAP(() => {
    playMenuOpenMotion();
  }, { dependencies: [playMenuOpenMotion], scope: rootRef });

  const runCloseMotion = useCallback(() => new Promise<void>((resolve) => {
    const menu = rootRef.current?.querySelector("[data-motion='orb-menu']");
    const items = rootRef.current?.querySelectorAll("[data-motion='orb-menu-item']");

    gsap.timeline({
      defaults: { ease: motion.ease.in },
      onComplete: () => {
        void hideCurrentWindow().then(() => {
          resetMenuMotionTargets();
          const afterClose = afterCloseRef.current;
          afterCloseRef.current = undefined;
          return afterClose?.();
        }).finally(() => {
          resolve();
        });
      }
    })
      .to(items ?? [], {
        autoAlpha: 0,
        y: -2,
        duration: getMotionDuration(0.08, reduceMotion),
        stagger: reduceMotion ? 0 : 0.015
      })
      .to(menu ?? rootRef.current, {
        autoAlpha: 0,
        scale: 0.97,
        duration: getMotionDuration(0.12, reduceMotion)
      }, "<0.03");
  }), [reduceMotion, resetMenuMotionTargets]);

  const { closeWindow: closeMenuWithMotion } = useWindowLifecycle({
    onOpen: playMenuOpenMotion,
    onClose: runCloseMotion,
    closeOnBlur: true
  });

  async function openSettings() {
    afterCloseRef.current = () => showWindow("settings");
    await closeMenuWithMotion();
  }

  async function openKnowledge() {
    afterCloseRef.current = () => showWindow("knowledge");
    await closeMenuWithMotion();
  }

  function animateMenuItem(event: ReactMouseEvent<HTMLButtonElement>, hovered: boolean) {
    const icon = event.currentTarget.querySelector("svg");
    const label = event.currentTarget.querySelector("span");
    gsap.to([icon, label], {
      x: hovered ? 2 : 0,
      duration: motion.duration.fast,
      ease: motion.ease.out
    });
  }

  return (
    <main ref={rootRef} className="context-menu-stage" onContextMenu={(event) => event.preventDefault()}>
      <nav className="orb-menu" aria-label="悬浮球菜单" data-motion="orb-menu">
        <button
          className="orb-menu-item is-active"
          data-motion="orb-menu-item"
          onClick={openSettings}
          onPointerEnter={(event) => animateMenuItem(event, true)}
          onPointerLeave={(event) => animateMenuItem(event, false)}
        >
          <Settings size={17} />
          <span>设置</span>
        </button>
        <button
          className="orb-menu-item"
          data-motion="orb-menu-item"
          onClick={openKnowledge}
          onPointerEnter={(event) => animateMenuItem(event, true)}
          onPointerLeave={(event) => animateMenuItem(event, false)}
        >
          <BookOpen size={17} />
          <span>知识库</span>
        </button>
        <button
          className="orb-menu-item"
          data-motion="orb-menu-item"
          onPointerEnter={(event) => animateMenuItem(event, true)}
          onPointerLeave={(event) => animateMenuItem(event, false)}
        >
          <User size={17} />
          <span>个人信息</span>
        </button>
        <button
          className="orb-menu-item"
          data-motion="orb-menu-item"
          onPointerEnter={(event) => animateMenuItem(event, true)}
          onPointerLeave={(event) => animateMenuItem(event, false)}
        >
          <History size={17} />
          <span>任务历史</span>
        </button>
        <div className="orb-menu-divider" data-motion="orb-menu-divider" />
        <button
          className="orb-menu-item"
          data-motion="orb-menu-item"
          onPointerEnter={(event) => animateMenuItem(event, true)}
          onPointerLeave={(event) => animateMenuItem(event, false)}
        >
          <Power size={17} />
          <span>退出 DeskPilot</span>
        </button>
      </nav>
    </main>
  );
}
