import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Clock3, Copy, Info, Keyboard, PanelRight, Settings, ShieldCheck, User, X } from "lucide-react";
import { Flip, gsap, useGSAP } from "../motion/register";
import { getMotionDuration, motion } from "../motion/constants";
import { useReducedMotion } from "../motion/useReducedMotion";
import { useWindowLifecycle } from "../hooks/useWindowLifecycle";
import { hideCurrentWindow } from "./windowActions";

const settingsNav = [
  { label: "账号", icon: User },
  { label: "通用", icon: Settings },
  { label: "悬浮球", icon: PanelRight },
  { label: "快捷键", icon: Keyboard },
  { label: "上下文权限", icon: ShieldCheck },
  { label: "AI 设置", icon: Bot },
  { label: "关于", icon: Info }
];
export function SettingsView() {
  const rootRef = useRef<HTMLElement | null>(null);
  const [active, setActive] = useState("账号");
  const [displayedActive, setDisplayedActive] = useState("账号");
  const switchingRef = useRef(false);
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
    gsap.set(targets, { autoAlpha: 1, clearProps: "visibility" });
    gsap.set(targets, { x: 0, y: 0, scale: 1 });

    gsap.timeline({ defaults: { ease: motion.ease.out } })
      .fromTo(sidebar ?? [], { x: -14 }, { x: 0, duration: getMotionDuration(0.2, reduceMotion) }, 0)
      .fromTo(logo ?? [], { y: -4 }, { y: 0, duration: getMotionDuration(0.16, reduceMotion) }, 0.05)
      .from(navItems ?? [], {
        x: -8,
        duration: getMotionDuration(0.16, reduceMotion),
        stagger: reduceMotion ? 0 : motion.stagger.tight
      }, 0.08)
      .fromTo(content ?? [], { y: 10 }, { y: 0, duration: getMotionDuration(0.2, reduceMotion) }, 0.1)
      .from(pageItems ?? [], {
        y: 8,
        duration: getMotionDuration(0.16, reduceMotion),
        stagger: reduceMotion ? 0 : motion.stagger.normal
      }, 0.16);
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
      y: 8,
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
    const card = rootRef.current?.querySelector("[data-motion='settings-card']");
    const state = card ? Flip.getState(card) : null;

    gsap.timeline({
      defaults: { ease: motion.ease.out },
      onComplete: () => {
        setDisplayedActive(nextActive);
        window.setTimeout(() => {
          if (state && card) {
            Flip.from(state, {
              targets: card,
              duration: getMotionDuration(0.18, reduceMotion),
              ease: motion.ease.out,
              simple: true
            });
          }
          switchingRef.current = false;
        }, 0);
      }
    })
      .to(rootRef.current?.querySelector("[data-motion='settings-card-body']") ?? [], {
        autoAlpha: 0,
        y: -6,
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
        y: 8,
        duration: getMotionDuration(0.12, reduceMotion)
      }, 0)
      .to(rootRef.current?.querySelectorAll("[data-motion='settings-nav-item']") ?? [], {
        autoAlpha: 0,
        x: -4,
        duration: getMotionDuration(0.1, reduceMotion),
        stagger: reduceMotion ? 0 : 0.015
      }, 0.02)
      .to(rootRef.current?.querySelector("[data-motion='settings-sidebar']") ?? [], {
        autoAlpha: 0,
        x: -8,
        duration: getMotionDuration(0.12, reduceMotion)
      }, 0.06)
      .to(rootRef.current ?? [], {
        autoAlpha: 0,
        duration: getMotionDuration(0.12, reduceMotion)
      }, 0.08);
  }), [reduceMotion, resetSettingsMotionTargets]);

  const { closeWindow: closeSettingsWithMotion } = useWindowLifecycle({
    onOpen: playSettingsOpenMotion,
    onClose: runCloseMotion
  });

  return (
    <main ref={rootRef} className="settings-stage" data-motion="settings-stage">
      <aside className="settings-sidebar" data-motion="settings-sidebar">
        <div className="settings-logo" data-motion="settings-logo">
          <span className="settings-logo-mark">D</span>
          <strong>DeskPilot</strong>
        </div>
        <nav>
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
          <div className="window-dots">
            <span />
            <span />
            <button onClick={() => void closeSettingsWithMotion()} title="关闭">
              <X size={18} />
            </button>
          </div>
        </header>

        <div className="settings-card" data-motion="settings-card">
          <div data-motion="settings-card-body">
            <h1 data-motion="settings-page-item">{displayedActive}</h1>
            {displayedActive === "账号" ? <AccountSettings /> : <GenericSettings active={displayedActive} />}
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
          <h2>本地模式 <span>本地</span></h2>
          <p>数据仅保存在此设备</p>
        </div>
      </div>

      <div className="settings-list">
        <div className="settings-list-row" data-motion="settings-page-item">
          <User size={18} />
          <span>用户名</span>
          <strong>Demo User</strong>
        </div>
        <div className="settings-list-row" data-motion="settings-page-item">
          <Copy size={18} />
          <span>本地用户 ID</span>
          <strong>a1e4f7b2-6d9c-4f18-b8d3</strong>
        </div>
        <div className="settings-list-row" data-motion="settings-page-item">
          <Clock3 size={18} />
          <span>模型服务状态</span>
          <strong className="is-running">运行中</strong>
        </div>
      </div>
      <div className="settings-pagination" data-motion="settings-page-item">
        <span className="is-active" />
        <span />
        <span />
        <span />
        <span />
      </div>
    </div>
  );
}

function GenericSettings({ active }: { active: string }) {
  const toggleRef = useRef<HTMLButtonElement | null>(null);
  const [enabled, setEnabled] = useState(true);

  useEffect(() => {
    gsap.to(toggleRef.current ?? [], {
      backgroundColor: enabled ? "var(--color-accent)" : "#cbd5e1",
      duration: motion.duration.base,
      ease: motion.ease.out
    });
    gsap.to(toggleRef.current?.querySelector("[data-motion='toggle-knob']") ?? [], {
      x: enabled ? 18 : 0,
      duration: motion.duration.base,
      ease: motion.ease.out
    });
  }, [enabled]);

  return (
    <div className="generic-settings">
      <div className="empty-setting-icon" data-motion="settings-page-item">
        <Settings size={30} />
      </div>
      <h2 data-motion="settings-page-item">{active}配置</h2>
      <p data-motion="settings-page-item">这里用于承载 {active} 的配置项。第一版先完成页面结构，后续接入真实设置读写。</p>
      <div className="setting-toggle-row" data-motion="settings-page-item">
        <span>启用此模块</span>
        <button
          ref={toggleRef}
          className={enabled ? "toggle is-on" : "toggle"}
          aria-label="启用此模块"
          onClick={() => setEnabled((value) => !value)}
        >
          <span className="toggle-knob" data-motion="toggle-knob" />
        </button>
      </div>
    </div>
  );
}
