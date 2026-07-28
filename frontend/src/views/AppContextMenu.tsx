import { CSSProperties, KeyboardEvent, PointerEvent, ReactNode, useEffect, useRef } from "react";
import { gsap, useGSAP } from "../motion/register";
import { getMotionDuration, motion } from "../motion/constants";
import { useReducedMotion } from "../motion/useReducedMotion";

export interface AppContextMenuItem {
  id: string;
  label: string;
  icon: ReactNode;
  onSelect: () => void | Promise<void>;
  hint?: string;
  disabled?: boolean;
  tone?: "default" | "danger";
}

export interface AppContextMenuGroup {
  id: string;
  items: AppContextMenuItem[];
}

interface AppContextMenuProps {
  ariaLabel: string;
  groups: AppContextMenuGroup[];
  className?: string;
  autoFocus?: boolean;
  animate?: boolean;
  onEscape?: () => void;
  onPointerDown?: (event: PointerEvent<HTMLDivElement>) => void;
  style?: CSSProperties;
}

function enabledItems(menu: HTMLElement | null) {
  if (!menu) return [];
  return Array.from(menu.querySelectorAll<HTMLButtonElement>("[role='menuitem']:not(:disabled)"));
}

export function AppContextMenu({
  ariaLabel,
  groups,
  className = "",
  autoFocus = true,
  animate = true,
  onEscape,
  onPointerDown,
  style
}: AppContextMenuProps) {
  const menuRef = useRef<HTMLDivElement | null>(null);
  const reduceMotion = useReducedMotion();
  const firstEnabledItemId = groups.flatMap((group) => group.items).find((item) => !item.disabled)?.id;

  useEffect(() => {
    if (!autoFocus) return;
    const frame = window.requestAnimationFrame(() => enabledItems(menuRef.current)[0]?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [autoFocus]);

  useGSAP(() => {
    if (!animate || !menuRef.current) return;
    const items = enabledItems(menuRef.current);
    gsap.timeline({ defaults: { ease: motion.ease.out } })
      .fromTo(menuRef.current, {
        autoAlpha: 0,
        scale: 0.96,
        y: 4,
        transformOrigin: "top left"
      }, {
        autoAlpha: 1,
        scale: 1,
        y: 0,
        duration: getMotionDuration(motion.duration.base, reduceMotion)
      })
      .from(items, {
        autoAlpha: 0,
        x: -3,
        duration: getMotionDuration(motion.duration.fast, reduceMotion),
        stagger: reduceMotion ? 0 : motion.stagger.tight
      }, "<0.03");
  }, { dependencies: [animate, reduceMotion], scope: menuRef });

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const menu = menuRef.current;
    if (!menu) return;
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      onEscape?.();
      return;
    }
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;

    event.preventDefault();
    const items = enabledItems(menu);
    if (!items.length) return;
    const currentIndex = items.indexOf(document.activeElement as HTMLButtonElement);
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? items.length - 1
        : event.key === "ArrowDown"
          ? (currentIndex + 1 + items.length) % items.length
          : (currentIndex - 1 + items.length) % items.length;
    items[nextIndex]?.focus();
  }

  return (
    <div
      ref={menuRef}
      className={`app-context-menu ${className}`.trim()}
      role="menu"
      aria-label={ariaLabel}
      onKeyDown={handleKeyDown}
      onPointerDown={onPointerDown}
      style={style}
      data-motion="context-menu"
    >
      {groups.map((group, groupIndex) => (
        <div key={group.id} className="app-context-menu-group" role="group">
          {groupIndex > 0 ? <div className="app-context-menu-separator" role="separator" data-motion="context-menu-divider" /> : null}
          {group.items.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`app-context-menu-item${item.tone === "danger" ? " is-danger" : ""}`}
              role="menuitem"
              disabled={item.disabled}
              tabIndex={!item.disabled && item.id === firstEnabledItemId ? 0 : -1}
              onClick={() => void item.onSelect()}
              data-motion="context-menu-item"
            >
              <span className="app-context-menu-icon" aria-hidden="true">{item.icon}</span>
              <span className="app-context-menu-label">{item.label}</span>
              {item.hint ? <span className="app-context-menu-hint">{item.hint}</span> : null}
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}
