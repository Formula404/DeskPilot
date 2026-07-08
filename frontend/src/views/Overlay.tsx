import { FormEvent, MouseEvent as ReactMouseEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bot, Copy, FileText, LayoutGrid } from "lucide-react";
import { cancelTask, createTask, openEventStream } from "../api/client";
import type { TaskEvent } from "../types/api";
import type { SuggestedAction, OverlayMode } from "../types/window";
import { useTaskStore } from "../store/taskStore";
import { gsap, useGSAP } from "../motion/register";
import { getMotionDuration, motion } from "../motion/constants";
import { useReducedMotion } from "../motion/useReducedMotion";
import { useWindowLifecycle } from "../hooks/useWindowLifecycle";
import { CommandComposer } from "./CommandComposer";
import { TaskExecutionPanel } from "./TaskPanel";
import { hideCurrentWindow } from "./windowActions";

const suggestedActions: SuggestedAction[] = [
  {
    id: "summarize",
    label: "总结当前网页",
    prompt: "总结当前网页并保存为 Markdown",
    icon: FileText
  },
  {
    id: "table",
    label: "提取表格",
    prompt: "提取当前网页中的表格并保存为 Excel",
    icon: LayoutGrid
  },
  {
    id: "markdown",
    label: "保存为 Markdown",
    prompt: "把当前网页整理成 Markdown 笔记",
    icon: Copy
  },
  {
    id: "translate",
    label: "翻译页面",
    prompt: "翻译当前页面的主要内容",
    icon: Bot
  }
];
export function OverlayView() {
  const rootRef = useRef<HTMLElement | null>(null);
  const ignoreBlurUntilRef = useRef(0);
  const [message, setMessage] = useState("");
  const [isCreatingTask, setIsCreatingTask] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [composerSignal, setComposerSignal] = useState<"idle" | "submit" | "error">("idle");
  const reduceMotion = useReducedMotion();
  const { events, addEvent, clearEvents, currentTaskId, setCurrentTaskId } = useTaskStore();
  const currentTaskEvents = useMemo(
    () => events.filter((event) => !currentTaskId || event.task_id === currentTaskId || event.task_id === null),
    [currentTaskId, events]
  );
  const mode = useMemo<OverlayMode>(() => {
    if (isCreatingTask) return "creating";
    if (currentTaskEvents.some((event) => event.type === "task.failed")) return "failed";
    if (currentTaskEvents.some((event) => event.type === "task.cancelled")) return "cancelled";
    if (currentTaskEvents.some((event) => event.type === "task.completed")) return "completed";
    if (currentTaskId) return "running";
    return "idle";
  }, [currentTaskEvents, currentTaskId, isCreatingTask]);

  const playOverlayOpenMotion = useCallback(() => {
    ignoreBlurUntilRef.current = Date.now() + 350;
    const overlay = rootRef.current;
    const gradient = rootRef.current?.querySelector("[data-motion='overlay-gradient']");
    const suggestions = rootRef.current?.querySelectorAll("[data-motion='suggestion-item']");
    const composer = rootRef.current?.querySelector("[data-motion='command-composer']");
    const spark = rootRef.current?.querySelector("[data-motion='composer-spark']");

    if (!overlay || !gradient || !composer) {
      return;
    }

    const targets = [
      overlay,
      gradient,
      composer,
      ...(spark ? [spark] : []),
      ...Array.from(suggestions ?? [])
    ];
    gsap.killTweensOf(targets);
    gsap.set(targets, { autoAlpha: 1, clearProps: "visibility" });
    gsap.set(overlay, { x: 0, y: 0, scale: 1 });
    gsap.set([gradient, composer, ...(suggestions ? Array.from(suggestions) : [])], { x: 0, y: 0, scale: 1 });

    gsap.timeline({ defaults: { ease: motion.ease.out } })
      .fromTo(gradient, {
        y: 24,
      }, {
        y: 0,
        duration: getMotionDuration(motion.duration.panel, reduceMotion)
      }, 0)
      .fromTo(suggestions ?? [], {
        y: 12,
        scale: 0.98,
      }, {
        y: 0,
        scale: 1,
        duration: getMotionDuration(motion.duration.base, reduceMotion),
        stagger: reduceMotion ? 0 : 0.035
      }, 0.08)
      .fromTo(composer, {
        y: 18,
        scale: 0.985,
      }, {
        y: 0,
        scale: 1,
        duration: getMotionDuration(0.22, reduceMotion)
      }, 0.13)
      .fromTo(spark ?? [], {
        rotation: -18,
        scale: 0.85,
      }, {
        rotation: 0,
        scale: 1,
        duration: getMotionDuration(0.16, reduceMotion)
      }, 0.18);
  }, [reduceMotion]);

  const resetOverlayMotionTargets = useCallback(() => {
    const overlay = rootRef.current;
    const panel = rootRef.current?.querySelector("[data-motion='task-panel']");
    const suggestions = rootRef.current?.querySelectorAll("[data-motion='suggestion-item']");
    const composer = rootRef.current?.querySelector("[data-motion='command-composer']");
    const gradient = rootRef.current?.querySelector("[data-motion='overlay-gradient']");
    const spark = rootRef.current?.querySelector("[data-motion='composer-spark']");
    const targets = [
      ...(overlay ? [overlay] : []),
      ...(panel ? [panel] : []),
      ...(composer ? [composer] : []),
      ...(gradient ? [gradient] : []),
      ...(spark ? [spark] : []),
      ...Array.from(suggestions ?? [])
    ];

    gsap.killTweensOf(targets);
    gsap.set(targets, {
      autoAlpha: 1,
      x: 0,
      y: 0,
      scale: 1,
      rotation: 0,
      clearProps: "visibility"
    });
  }, []);

  useGSAP(() => {
    playOverlayOpenMotion();
  }, { dependencies: [playOverlayOpenMotion], scope: rootRef });

  useGSAP(() => {
    const statusMessage = rootRef.current?.querySelector("[data-motion='status-message']");
    if (!statusMessage || (!actionError && !streamError)) {
      return;
    }
    gsap.fromTo(statusMessage, {
      autoAlpha: 0,
      y: 8
    }, {
      autoAlpha: 1,
      y: 0,
      duration: getMotionDuration(motion.duration.base, reduceMotion),
      ease: motion.ease.out
    });
  }, { dependencies: [actionError, streamError, reduceMotion], scope: rootRef });

  const runCloseMotion = useCallback(() => new Promise<void>((resolve) => {
    const panel = rootRef.current?.querySelector("[data-motion='task-panel']");
    const suggestions = rootRef.current?.querySelectorAll("[data-motion='suggestion-item']");
    const composer = rootRef.current?.querySelector("[data-motion='command-composer']");
    const gradient = rootRef.current?.querySelector("[data-motion='overlay-gradient']");

    gsap.timeline({
      defaults: { ease: motion.ease.in },
      onComplete: () => {
        void hideCurrentWindow().then(resetOverlayMotionTargets).finally(resolve);
      }
    })
      .to(panel ?? [], {
        autoAlpha: 0,
        x: 8,
        duration: getMotionDuration(0.1, reduceMotion)
      }, 0)
      .to(suggestions ?? [], {
        autoAlpha: 0,
        y: 6,
        duration: getMotionDuration(0.1, reduceMotion),
        stagger: reduceMotion ? 0 : 0.015
      }, 0)
      .to(composer ?? [], {
        autoAlpha: 0,
        y: 12,
        scale: 0.99,
        duration: getMotionDuration(0.12, reduceMotion)
      }, 0.02)
      .to(gradient ?? [], {
        autoAlpha: 0,
        y: 18,
        duration: getMotionDuration(0.12, reduceMotion)
      }, 0.05)
      .to(rootRef.current, {
        autoAlpha: 0,
        duration: getMotionDuration(0.12, reduceMotion)
      }, 0.1);
  }), [reduceMotion, resetOverlayMotionTargets]);

  const { closeWindow: closeOverlayWithMotion } = useWindowLifecycle({
    onOpen: playOverlayOpenMotion,
    onClose: runCloseMotion,
    closeOnBlur: true,
    shouldIgnoreClose: () => Date.now() < ignoreBlurUntilRef.current
  });

  useEffect(() => {
    const source = openEventStream(
      (event) => {
        setStreamError(null);
        addEvent(event);
      },
      () => setStreamError("任务事件连接异常，正在尝试自动重连")
    );
    return () => source.close();
  }, [addEvent]);

  async function submitTask(nextMessage: string) {
    const trimmed = nextMessage.trim();
    if (!trimmed || isCreatingTask) {
      if (!trimmed) {
        setComposerSignal("error");
        window.setTimeout(() => setComposerSignal("idle"), 0);
      }
      return;
    }
    setComposerSignal("submit");
    window.setTimeout(() => setComposerSignal("idle"), 0);
    setIsCreatingTask(true);
    setActionError(null);
    clearEvents();
    setCurrentTaskId(null);
    try {
      const response = await createTask(trimmed);
      setCurrentTaskId(response.task_id);
      setMessage("");
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "创建任务失败");
      setComposerSignal("error");
      window.setTimeout(() => setComposerSignal("idle"), 0);
    } finally {
      setIsCreatingTask(false);
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    await submitTask(message);
  }

  async function stopTask() {
    if (currentTaskId) {
      setActionError(null);
      try {
        await cancelTask(currentTaskId);
      } catch (error) {
        setActionError(error instanceof Error ? error.message : "停止任务失败");
        setComposerSignal("error");
        window.setTimeout(() => setComposerSignal("idle"), 0);
      }
    }
  }

  function animateSuggestion(event: ReactMouseEvent<HTMLButtonElement>, hovered: boolean) {
    const icon = event.currentTarget.querySelector("svg");
    gsap.to(event.currentTarget, {
      y: hovered ? -2 : 0,
      scale: hovered ? 1.012 : 1,
      duration: motion.duration.fast,
      ease: motion.ease.out
    });
    gsap.to(icon, {
      scale: hovered ? 1.08 : 1,
      rotation: hovered ? -2 : 0,
      duration: motion.duration.fast,
      ease: motion.ease.out
    });
  }

  async function submitSuggestedAction(prompt: string, target: HTMLButtonElement) {
    const siblings = Array.from(rootRef.current?.querySelectorAll("[data-motion='suggestion-item']") ?? [])
      .filter((item) => item !== target);
    gsap.timeline({ defaults: { ease: motion.ease.out } })
      .to(target, { scale: 0.98, duration: motion.duration.micro })
      .to(target, { scale: 1, duration: motion.duration.fast })
      .to(siblings, { autoAlpha: 0.38, y: 4, duration: motion.duration.fast }, 0.04);
    await submitTask(prompt);
  }

  return (
    <main
      ref={rootRef}
      className="overlay-stage"
      data-motion="overlay"
      onMouseDownCapture={(event) => {
        const target = event.target as HTMLElement;
        if (!target.closest("[data-overlay-interactive='true']")) {
          void closeOverlayWithMotion();
        }
      }}
    >
      <div className="overlay-gradient" data-motion="overlay-gradient" />
      <section className="overlay-workspace">
        {mode !== "idle" ? (
          <TaskExecutionPanel events={currentTaskEvents} mode={mode} />
        ) : null}

        <section className="composer-area">
          {actionError || streamError ? (
            <div className="overlay-status-message" data-overlay-interactive="true" data-motion="status-message">
              {actionError ?? streamError}
            </div>
          ) : null}
          <div className="suggestion-row" data-overlay-interactive="true">
            {suggestedActions.map((action) => {
              const Icon = action.icon;
              return (
                <button
                  key={action.id}
                  className={`suggestion-button suggestion-button-${action.id}`}
                  data-motion="suggestion-item"
                  disabled={isCreatingTask}
                  onClick={(event) => submitSuggestedAction(action.prompt, event.currentTarget)}
                  onPointerEnter={(event) => animateSuggestion(event, true)}
                  onPointerLeave={(event) => animateSuggestion(event, false)}
                >
                  <Icon size={20} />
                  <span>{action.label}</span>
                </button>
              );
            })}
          </div>
          <CommandComposer
            message={message}
            mode={mode}
            disabled={isCreatingTask}
            signal={composerSignal}
            onChange={setMessage}
            onSubmit={onSubmit}
            onStop={stopTask}
          />
        </section>
      </section>
    </main>
  );
}
