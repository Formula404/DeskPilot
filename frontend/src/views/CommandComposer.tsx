import { FormEvent, useRef } from "react";
import { ArrowUp, Clock3, Sparkles, Square } from "lucide-react";
import type { OverlayMode } from "../types/window";
import { gsap, useGSAP } from "../motion/register";
import { getMotionDuration, motion } from "../motion/constants";
import { useReducedMotion } from "../motion/useReducedMotion";
export function CommandComposer({
  message,
  mode,
  disabled,
  signal,
  onChange,
  onSubmit,
  onStop
}: {
  message: string;
  mode: OverlayMode;
  disabled?: boolean;
  signal: "idle" | "submit" | "error";
  onChange: (message: string) => void;
  onSubmit: (event: FormEvent) => void;
  onStop: () => void;
}) {
  const rootRef = useRef<HTMLFormElement | null>(null);
  const loadingTimelineRef = useRef<gsap.core.Timeline | null>(null);
  const reduceMotion = useReducedMotion();
  const running = mode === "running";
  const creating = mode === "creating";
  const canSend = Boolean(message.trim()) && !disabled && !creating;

  useGSAP(() => {
    const arrow = rootRef.current?.querySelector("[data-motion='send-icon-arrow']");
    const clock = rootRef.current?.querySelector("[data-motion='send-icon-clock']");
    const stop = rootRef.current?.querySelector("[data-motion='send-icon-stop']");
    const spark = rootRef.current?.querySelector("[data-motion='composer-spark']");
    const button = rootRef.current?.querySelector("[data-motion='composer-send']");

    if (!arrow || !clock || !stop || !button) {
      return;
    }

    loadingTimelineRef.current?.kill();
    gsap.set([arrow, clock, stop], { transformOrigin: "50% 50%" });

    const active = running ? stop : creating ? clock : arrow;
    const inactive = [arrow, clock, stop].filter((item) => item !== active);

    gsap.timeline({ defaults: { ease: motion.ease.out } })
      .to(inactive, {
        autoAlpha: 0,
        scale: 0.78,
        rotation: -12,
        duration: getMotionDuration(motion.duration.fast, reduceMotion)
      }, 0)
      .fromTo(active, {
        autoAlpha: 0,
        scale: 0.78,
        rotation: creating ? -30 : running ? 12 : 0
      }, {
        autoAlpha: 1,
        scale: 1,
        rotation: 0,
        duration: getMotionDuration(motion.duration.base, reduceMotion)
      }, 0)
      .to(button, {
        scale: canSend || running || creating ? 1 : 0.96,
        autoAlpha: canSend || running || creating ? 1 : 0.72,
        duration: getMotionDuration(motion.duration.fast, reduceMotion)
      }, 0);

    if (creating && !reduceMotion) {
      loadingTimelineRef.current = gsap.timeline({ repeat: -1 })
        .to(clock, { rotation: 360, duration: 1.1, ease: motion.ease.none });
    }

    if (spark && !reduceMotion && canSend) {
      gsap.timeline()
        .to(spark, { scale: 1.08, rotation: 8, duration: 0.1, ease: motion.ease.out })
        .to(spark, { scale: 1, rotation: 0, duration: 0.14, ease: motion.ease.out });
    }

    return () => loadingTimelineRef.current?.kill();
  }, { dependencies: [canSend, creating, reduceMotion, running], scope: rootRef });

  useGSAP(() => {
    if (signal === "idle") {
      return;
    }
    if (signal === "submit") {
      gsap.timeline()
        .to(rootRef.current, { y: -2, duration: 0.06, ease: motion.ease.out })
        .to(rootRef.current, { y: 0, duration: 0.12, ease: motion.ease.out });
      return;
    }

    gsap.to(rootRef.current, {
      keyframes: [
        { x: -3, duration: 0.04 },
        { x: 3, duration: 0.05 },
        { x: -2, duration: 0.04 },
        { x: 0, duration: 0.05 }
      ],
      ease: motion.ease.out
    });
  }, { dependencies: [signal], scope: rootRef });

  return (
    <form ref={rootRef} className="command-composer" onSubmit={onSubmit} data-overlay-interactive="true" data-motion="command-composer">
      <Sparkles className="composer-spark" size={28} data-motion="composer-spark" />
      <input
        autoFocus
        disabled={disabled}
        value={message}
        onChange={(event) => onChange(event.target.value)}
        onFocus={() => {
          gsap.timeline()
            .to(rootRef.current, { y: -1, scale: 1.004, duration: motion.duration.fast, ease: motion.ease.out })
            .to(rootRef.current, { y: 0, scale: 1, duration: motion.duration.base, ease: motion.ease.out });
        }}
        placeholder="输入你想让 DeskPilot 做的事..."
      />
      <button
        className={running ? "composer-send is-stop" : "composer-send"}
        data-motion="composer-send"
        disabled={creating || disabled}
        type={running ? "button" : "submit"}
        onClick={running ? onStop : undefined}
        title={running ? "停止任务" : creating ? "创建任务中" : "发送"}
      >
        <span className="send-icon send-icon-arrow" data-motion="send-icon-arrow">
          <ArrowUp size={24} />
        </span>
        <span className="send-icon send-icon-clock" data-motion="send-icon-clock">
          <Clock3 size={22} />
        </span>
        <span className="send-icon send-icon-stop" data-motion="send-icon-stop">
          <Square size={20} />
        </span>
      </button>
    </form>
  );
}
