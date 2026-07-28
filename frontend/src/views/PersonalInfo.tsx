import { MouseEvent as ReactMouseEvent, useCallback, useRef } from "react";
import { Window } from "@tauri-apps/api/window";
import { ShieldCheck, UserRound, X } from "lucide-react";
import deskpilotLogo from "../assets/deskpilot-logo.png";
import { gsap, useGSAP } from "../motion/register";
import { getMotionDuration, motion } from "../motion/constants";
import { useReducedMotion } from "../motion/useReducedMotion";
import { useWindowLifecycle } from "../hooks/useWindowLifecycle";
import { hideCurrentWindow, isTauriRuntime } from "./windowActions";
import { PersonalInfoSettingsPanel } from "./PersonalInfoSettings";

export function PersonalInfoView() {
  const rootRef = useRef<HTMLElement | null>(null);
  const reduceMotion = useReducedMotion();

  const resetMotionTargets = useCallback(() => {
    const root = rootRef.current;
    const shell = root?.querySelector("[data-motion='personal-info-shell']");
    const content = root?.querySelector("[data-motion='personal-info-content']");
    const targets = [root, shell, content].filter(Boolean);
    gsap.killTweensOf(targets);
    gsap.set(targets, {
      autoAlpha: 1,
      x: 0,
      y: 0,
      scale: 1,
      clearProps: "opacity,visibility,transform",
    });
  }, []);

  const playOpenMotion = useCallback(() => {
    const root = rootRef.current;
    const shell = root?.querySelector("[data-motion='personal-info-shell']");
    const content = root?.querySelector("[data-motion='personal-info-content']");
    if (!root) return;
    gsap.killTweensOf([root, shell, content]);
    gsap.set([root, shell, content], { clearProps: "visibility" });
    gsap.timeline({ defaults: { ease: motion.ease.out } })
      .fromTo(root, { autoAlpha: 0 }, { autoAlpha: 1, duration: getMotionDuration(0.14, reduceMotion) })
      .fromTo(shell ?? [], { y: 6, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: getMotionDuration(0.18, reduceMotion) }, 0.02)
      .fromTo(content ?? [], { autoAlpha: 0 }, { autoAlpha: 1, duration: getMotionDuration(0.16, reduceMotion) }, 0.08);
  }, [reduceMotion]);

  const handleWindowOpen = useCallback(() => {
    playOpenMotion();
    window.dispatchEvent(new Event("deskpilot:personal-info-refresh"));
  }, [playOpenMotion]);

  useGSAP(() => playOpenMotion(), { dependencies: [playOpenMotion], scope: rootRef });

  const runCloseMotion = useCallback(() => new Promise<void>((resolve) => {
    gsap.to(rootRef.current ?? [], {
      autoAlpha: 0,
      duration: getMotionDuration(0.12, reduceMotion),
      ease: motion.ease.in,
      onComplete: () => {
        void hideCurrentWindow().finally(() => {
          resetMotionTargets();
          resolve();
        });
      },
    });
  }), [reduceMotion, resetMotionTargets]);

  const { closeWindow } = useWindowLifecycle({
    onOpen: handleWindowOpen,
    onClose: runCloseMotion,
    replayOnFocus: true,
  });

  function startWindowDrag(event: ReactMouseEvent<HTMLElement>) {
    if (event.button !== 0 || !isTauriRuntime()) return;
    if ((event.target as HTMLElement).closest("button,input,select,a,[data-no-window-drag]")) return;
    void Window.getCurrent().startDragging();
  }

  return <main ref={rootRef} className="personal-info-stage" onMouseDown={startWindowDrag}>
    <section className="personal-info-shell" data-motion="personal-info-shell">
      <header className="personal-info-titlebar">
        <div className="personal-info-brand"><img src={deskpilotLogo} alt="DeskPilot" /><span><UserRound size={16} />个人信息库</span></div>
        <button data-no-window-drag title="关闭" onClick={() => void closeWindow()}><X size={18} /></button>
      </header>
      <div className="personal-info-intro" data-no-window-drag>
        <div><ShieldCheck size={18} /><span><strong>本地保存，由你控制</strong><small>已确认信息可用于表单填写；聊天识别的候选信息需先确认。</small></span></div>
      </div>
      <div className="personal-info-content" data-motion="personal-info-content" data-no-window-drag>
        <PersonalInfoSettingsPanel />
      </div>
    </section>
  </main>;
}
