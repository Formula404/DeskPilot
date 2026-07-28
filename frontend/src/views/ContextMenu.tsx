import { useCallback, useRef } from "react";
import { BookOpen, LayoutDashboard, Power, Settings, User } from "lucide-react";
import { gsap, useGSAP } from "../motion/register";
import { getMotionDuration, motion } from "../motion/constants";
import { useReducedMotion } from "../motion/useReducedMotion";
import { useWindowLifecycle } from "../hooks/useWindowLifecycle";
import { hideCurrentWindow, quitApplication, showOverlayWindow, showWindow } from "./windowActions";
import { AppContextMenu, type AppContextMenuGroup } from "./AppContextMenu";
export function ContextMenuView() {
  const rootRef = useRef<HTMLElement | null>(null);
  const afterCloseRef = useRef<(() => Promise<void>) | undefined>(undefined);
  const reduceMotion = useReducedMotion();

  const playMenuOpenMotion = useCallback(() => {
    const menu = rootRef.current?.querySelector("[data-motion='context-menu']");
    const items = rootRef.current?.querySelectorAll("[data-motion='context-menu-item']");
    const divider = rootRef.current?.querySelector("[data-motion='context-menu-divider']");
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
    const menu = rootRef.current?.querySelector("[data-motion='context-menu']");
    const items = rootRef.current?.querySelectorAll("[data-motion='context-menu-item']");
    const divider = rootRef.current?.querySelector("[data-motion='context-menu-divider']");
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
    const menu = rootRef.current?.querySelector("[data-motion='context-menu']");
    const items = rootRef.current?.querySelectorAll("[data-motion='context-menu-item']");

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

  async function openPersonalInfo() {
    afterCloseRef.current = () => showWindow("personal-info");
    await closeMenuWithMotion();
  }

  async function openDeskPilot() {
    afterCloseRef.current = showOverlayWindow;
    await closeMenuWithMotion();
  }

  async function exitDeskPilot() {
    afterCloseRef.current = quitApplication;
    await closeMenuWithMotion();
  }

  const menuGroups: AppContextMenuGroup[] = [
    {
      id: "primary",
      items: [
        { id: "open", label: "打开主面板", icon: <LayoutDashboard size={17} />, onSelect: openDeskPilot },
        { id: "knowledge", label: "知识库", icon: <BookOpen size={17} />, onSelect: openKnowledge },
        { id: "personal-info", label: "个人信息", icon: <User size={17} />, onSelect: openPersonalInfo },
        { id: "settings", label: "设置", icon: <Settings size={17} />, onSelect: openSettings }
      ]
    },
    {
      id: "application",
      items: [
        { id: "quit", label: "退出 DeskPilot", icon: <Power size={17} />, onSelect: exitDeskPilot, tone: "danger" }
      ]
    }
  ];

  return (
    <main ref={rootRef} className="context-menu-stage" onContextMenu={(event) => event.preventDefault()}>
      <AppContextMenu
        ariaLabel="DeskPilot 快捷菜单"
        groups={menuGroups}
        className="orb-menu"
        animate={false}
        onEscape={() => void closeMenuWithMotion("escape")}
      />
    </main>
  );
}
