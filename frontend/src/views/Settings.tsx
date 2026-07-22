import { MouseEvent as ReactMouseEvent, useCallback, useRef, useState } from "react";
import { Window } from "@tauri-apps/api/window";
import { BookOpen, Bot, Clock3, Copy, Info, Keyboard, PanelRight, Settings, ShieldCheck, User, X } from "lucide-react";
import deskpilotLogo from "../assets/deskpilot-logo.png";
import { gsap, useGSAP } from "../motion/register";
import { getMotionDuration, motion } from "../motion/constants";
import { useReducedMotion } from "../motion/useReducedMotion";
import { useWindowLifecycle } from "../hooks/useWindowLifecycle";
import { hideCurrentWindow, isTauriRuntime } from "./windowActions";
import { KnowledgeSettingsPanel } from "./KnowledgeSettings";
import { ApplicationSettingsPanel } from "./ApplicationSettings";
import { ContextPrivacySettingsPanel } from "./ContextPrivacySettings";

const settingsNav = [
  { label: "账号", icon: User },
  { label: "通用", icon: Settings },
  { label: "悬浮球", icon: PanelRight },
  { label: "快捷键", icon: Keyboard },
  { label: "上下文权限", icon: ShieldCheck },
  { label: "AI 设置", icon: Bot },
  { label: "知识库", icon: BookOpen },
  { label: "关于", icon: Info }
];
export function SettingsView() {
  const rootRef = useRef<HTMLElement | null>(null);
  const [active, setActive] = useState("账号");
  const [displayedActive, setDisplayedActive] = useState("账号");
  const switchingRef = useRef(false);
  const dragStateRef = useRef<{ startX: number; startY: number; dragging: boolean } | null>(null);
  const reduceMotion = useReducedMotion();

  const playSettingsOpenMotion = useCallback(() => {
    const stage = rootRef.current;
    const sidebar = rootRef.current?.querySelector("[data-motion='settings-sidebar']");
    const logo = rootRef.current?.querySelector("[data-motion='settings-logo']");
    const navItems = rootRef.current?.querySelectorAll("[data-motion='settings-nav-item']");
    const content = rootRef.current?.querySelector("[data-motion='settings-content']");
    const pageItems = rootRef.current?.querySelectorAll("[data-motion='settings-page-item']");
    if (!stage) {
      return;
    }

    const targets = [
      stage,
      ...(sidebar ? [sidebar] : []),
      ...(logo ? [logo] : []),
      ...(content ? [content] : []),
      ...Array.from(navItems ?? []),
      ...Array.from(pageItems ?? [])
    ];
    gsap.killTweensOf(targets);
    gsap.set(targets, { x: 0, y: 0, scale: 1, clearProps: "visibility" });

    gsap.timeline({ defaults: { ease: motion.ease.out } })
      .fromTo(stage, { autoAlpha: 0 }, { autoAlpha: 1, duration: getMotionDuration(0.14, reduceMotion) }, 0)
      .fromTo(sidebar ?? [], { autoAlpha: 0 }, { autoAlpha: 1, duration: getMotionDuration(0.14, reduceMotion) }, 0)
      .fromTo(logo ?? [], { autoAlpha: 0 }, { autoAlpha: 1, duration: getMotionDuration(0.14, reduceMotion) }, 0.02)
      .from(navItems ?? [], {
        autoAlpha: 0,
        duration: getMotionDuration(0.16, reduceMotion),
        stagger: reduceMotion ? 0 : motion.stagger.tight
      }, 0.04)
      .fromTo(content ?? [], { autoAlpha: 0 }, { autoAlpha: 1, duration: getMotionDuration(0.16, reduceMotion) }, 0.05)
      .from(pageItems ?? [], {
        autoAlpha: 0,
        duration: getMotionDuration(0.16, reduceMotion),
        stagger: reduceMotion ? 0 : motion.stagger.normal
      }, 0.08);
  }, [reduceMotion]);

  const resetSettingsMotionTargets = useCallback(() => {
    const stage = rootRef.current;
    const sidebar = rootRef.current?.querySelector("[data-motion='settings-sidebar']");
    const logo = rootRef.current?.querySelector("[data-motion='settings-logo']");
    const navItems = rootRef.current?.querySelectorAll("[data-motion='settings-nav-item']");
    const content = rootRef.current?.querySelector("[data-motion='settings-content']");
    const pageItems = rootRef.current?.querySelectorAll("[data-motion='settings-page-item']");
    const cardBody = rootRef.current?.querySelector("[data-motion='settings-card-body']");
    const targets = [
      ...(stage ? [stage] : []),
      ...(sidebar ? [sidebar] : []),
      ...(logo ? [logo] : []),
      ...(content ? [content] : []),
      ...(cardBody ? [cardBody] : []),
      ...Array.from(navItems ?? []),
      ...Array.from(pageItems ?? [])
    ];

    gsap.killTweensOf(targets);
    gsap.set(targets, { autoAlpha: 1, x: 0, y: 0, scale: 1, rotation: 0, clearProps: "visibility" });
  }, []);

  useGSAP(() => {
    playSettingsOpenMotion();
  }, { dependencies: [playSettingsOpenMotion], scope: rootRef });

  useGSAP(() => {
    const pageItems = rootRef.current?.querySelectorAll("[data-motion='settings-page-item']");
    if (!pageItems?.length) {
      return;
    }
    gsap.from(pageItems, {
      autoAlpha: 0,
      duration: getMotionDuration(0.16, reduceMotion),
      stagger: reduceMotion ? 0 : motion.stagger.normal,
      ease: motion.ease.out
    });
  }, { dependencies: [displayedActive, reduceMotion], scope: rootRef });

  const switchSettingsPage = useCallback((nextActive: string) => {
    if (nextActive === displayedActive || switchingRef.current) {
      setActive(nextActive);
      return;
    }
    switchingRef.current = true;
    setActive(nextActive);

    gsap.timeline({
      defaults: { ease: motion.ease.out },
      onComplete: () => {
        setDisplayedActive(nextActive);
        window.requestAnimationFrame(() => {
          gsap.fromTo(rootRef.current?.querySelector("[data-motion='settings-card-body']") ?? [], {
            autoAlpha: 0
          }, {
            autoAlpha: 1,
            duration: getMotionDuration(0.12, reduceMotion),
            ease: motion.ease.out
          });
          switchingRef.current = false;
        });
      }
    })
      .to(rootRef.current?.querySelector("[data-motion='settings-card-body']") ?? [], {
        autoAlpha: 0,
        duration: getMotionDuration(0.1, reduceMotion)
      });
  }, [displayedActive, reduceMotion]);

  const runCloseMotion = useCallback(() => new Promise<void>((resolve) => {
    gsap.timeline({
      defaults: { ease: motion.ease.in },
      onComplete: () => {
        void hideCurrentWindow().then(resetSettingsMotionTargets).finally(resolve);
      }
    })
      .to(rootRef.current?.querySelector("[data-motion='settings-content']") ?? [], {
        autoAlpha: 0,
        duration: getMotionDuration(0.12, reduceMotion)
      }, 0)
      .to(rootRef.current?.querySelectorAll("[data-motion='settings-nav-item']") ?? [], {
        autoAlpha: 0,
        duration: getMotionDuration(0.1, reduceMotion),
        stagger: reduceMotion ? 0 : 0.015
      }, 0.02)
      .to(rootRef.current?.querySelector("[data-motion='settings-sidebar']") ?? [], {
        autoAlpha: 0,
        duration: getMotionDuration(0.12, reduceMotion)
      }, 0.06)
      .to(rootRef.current ?? [], {
        autoAlpha: 0,
        duration: getMotionDuration(0.12, reduceMotion)
      }, 0.08);
  }), [reduceMotion, resetSettingsMotionTargets]);

  const { closeWindow: closeSettingsWithMotion } = useWindowLifecycle({
    onOpen: playSettingsOpenMotion,
    onClose: runCloseMotion,
    replayOnFocus: false
  });

  function startWindowDrag(event: ReactMouseEvent<HTMLElement>) {
    if (event.button !== 0 || !isTauriRuntime()) {
      return;
    }
    if ((event.target as HTMLElement).closest("button, input, textarea, select, a, [data-no-window-drag]")) {
      return;
    }

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
      Window.getCurrent().startDragging().catch((error) => {
        console.warn("Failed to start dragging settings window", error);
      });
      cleanup();
    }

    function onMouseUp() {
      dragStateRef.current = null;
      cleanup();
    }

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  }

  return (
    <main ref={rootRef} className="settings-stage" data-motion="settings-stage" onMouseDown={startWindowDrag}>
      <aside className="settings-sidebar" data-motion="settings-sidebar">
        <div className="settings-logo" data-motion="settings-logo">
          <img src={deskpilotLogo} alt="DeskPilot" />
        </div>
        <nav data-no-window-drag>
          {settingsNav.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.label}
                className={active === item.label ? "settings-nav-item is-active" : "settings-nav-item"}
                data-motion="settings-nav-item"
                onClick={() => switchSettingsPage(item.label)}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <section className="settings-content" data-motion="settings-content">
        <header className="settings-window-bar">
          <span>设置页面</span>
          <div className="window-dots" data-no-window-drag>
            <span />
            <span />
            <button onClick={() => void closeSettingsWithMotion()} title="关闭">
              <X size={18} />
            </button>
          </div>
        </header>

        <div className="settings-card" data-motion="settings-card" data-no-window-drag>
          <div data-motion="settings-card-body">
            <h1>{displayedActive}</h1>
            {displayedActive === "账号" ? <AccountSettings />
              : displayedActive === "知识库" ? <KnowledgeSettingsPanel />
              : displayedActive === "AI 设置" ? <ApplicationSettingsPanel section="ai" />
              : displayedActive === "通用" ? <ApplicationSettingsPanel section="general" />
              : displayedActive === "上下文权限" ? <ContextPrivacySettingsPanel />
              : <GenericSettings active={displayedActive} />}
          </div>
        </div>
      </section>
    </main>
  );
}

function AccountSettings() {
  return (
    <div className="account-panel">
      <div className="profile-summary" data-motion="settings-page-item">
        <div className="avatar" data-motion="settings-page-item">D</div>
        <div>
          <h2>本地工作区 <span>本地</span></h2>
          <p>任务、知识库和用户设置仅保存在此设备</p>
        </div>
      </div>

      <div className="settings-list">
        <div className="settings-list-row" data-motion="settings-page-item">
          <User size={18} />
          <span>身份模式</span>
          <strong>无需登录</strong>
        </div>
        <div className="settings-list-row" data-motion="settings-page-item">
          <Copy size={18} />
          <span>敏感配置</span>
          <strong>Windows 用户级加密</strong>
        </div>
        <div className="settings-list-row" data-motion="settings-page-item">
          <Clock3 size={18} />
          <span>模型服务</span>
          <strong>在 AI 设置中管理</strong>
        </div>
      </div>
    </div>
  );
}

function GenericSettings({ active }: { active: string }) {
  return (
    <div className="generic-settings">
      <div className="empty-setting-icon" data-motion="settings-page-item">
        <Settings size={30} />
      </div>
      <h2 data-motion="settings-page-item">{active}配置</h2>
      <p data-motion="settings-page-item">{active}相关能力尚未开放，后续会沿用统一的版本化设置模型接入。</p>
    </div>
  );
}
