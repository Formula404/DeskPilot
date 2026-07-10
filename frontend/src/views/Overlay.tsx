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
import { isVisibleTaskStep } from "./taskStatus";
import { hideCurrentWindow, isTauriRuntime } from "./windowActions";

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
  const openTimelineRef = useRef<gsap.core.Timeline | null>(null);
  const streamErrorTimerRef = useRef<number | null>(null);
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
  const hasVisibleTaskSteps = useMemo(
    () => currentTaskEvents.some(isVisibleTaskStep),
    [currentTaskEvents]
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
    if (openTimelineRef.current?.isActive()) {
      return;
    }
    ignoreBlurUntilRef.current = Date.now() + 1200;
    const overlay = rootRef.current;
    const gradient = rootRef.current?.querySelector("[data-motion='overlay-gradient']");
    const scanBeam = rootRef.current?.querySelector("[data-motion='overlay-scan-beam']");
    const suggestions = rootRef.current?.querySelectorAll("[data-motion='suggestion-item']");
    const composer = rootRef.current?.querySelector("[data-motion='command-composer']");
    const spark = rootRef.current?.querySelector("[data-motion='composer-spark']");

    if (!overlay || !gradient || !scanBeam || !composer) {
      return;
    }

    const suggestionItems = Array.from(suggestions ?? []);
    const composerRect = composer.getBoundingClientRect();
    const composerStartY = Math.max(72, window.innerHeight - composerRect.top + 24);
    const targets = [
      overlay,
      gradient,
      scanBeam,
      composer,
      ...(spark ? [spark] : []),
      ...suggestionItems
    ];
    gsap.killTweensOf(targets);
    openTimelineRef.current?.kill();
    gsap.set(overlay, { autoAlpha: 1, x: 0, y: 0, scale: 1, clearProps: "visibility" });
    gsap.set(gradient, { autoAlpha: 0, x: 0, y: 18, scale: 1, clearProps: "visibility" });
    gsap.set(scanBeam, {
      autoAlpha: 0,
      x: 0,
      y: 0,
      yPercent: 58,
      scaleY: 1,
      transformOrigin: "50% 100%",
      clearProps: "visibility"
    });
    gsap.set(composer, {
      autoAlpha: 0,
      x: 0,
      y: composerStartY,
      scale: 0.985,
      transformOrigin: "50% 100%",
      clearProps: "visibility"
    });
    gsap.set(suggestionItems, {
      autoAlpha: 0,
      x: 0,
      y: 22,
      scale: 0.82,
      transformOrigin: "50% 100%",
      clearProps: "visibility"
    });
    gsap.set(spark ?? [], { autoAlpha: 0, rotation: -16, scale: 0.78, clearProps: "visibility" });

    openTimelineRef.current = gsap.timeline({
      defaults: { ease: motion.ease.out },
      onComplete: () => {
        openTimelineRef.current = null;
      }
    })
      .fromTo(gradient, {
        autoAlpha: 0,
        y: 18,
      }, {
        autoAlpha: 1,
        y: 0,
        duration: getMotionDuration(0.32, reduceMotion)
      }, 0)
      .fromTo(scanBeam, {
        autoAlpha: reduceMotion ? 0 : 0.18,
        yPercent: 58,
        scaleY: 1
      }, {
        autoAlpha: reduceMotion ? 0 : 0.86,
        yPercent: -62,
        scaleY: 1,
        duration: getMotionDuration(0.92, reduceMotion),
        ease: "power2.out"
      }, 0)
      .to(scanBeam, {
        autoAlpha: 0,
        duration: getMotionDuration(0.18, reduceMotion),
        ease: "power1.out"
      }, 0.78)
      .to(composer, {
        autoAlpha: 1,
        y: 0,
        scale: 1,
        duration: getMotionDuration(0.42, reduceMotion),
        ease: "power3.out"
      }, 0)
      .to(spark ?? [], {
        autoAlpha: 1,
        rotation: 0,
        scale: 1,
        duration: getMotionDuration(0.16, reduceMotion),
        ease: "back.out(1.45)"
      }, 0.28)
      .to(suggestionItems, {
        autoAlpha: 1,
        y: 0,
        scale: 1,
        duration: getMotionDuration(0.24, reduceMotion),
        stagger: reduceMotion ? 0 : 0.042,
        ease: "back.out(1.65)"
      }, 0.34);
  }, [reduceMotion]);

  const resetOverlayMotionTargets = useCallback(() => {
    const overlay = rootRef.current;
    const panel = rootRef.current?.querySelector("[data-motion='task-panel']");
    const suggestions = rootRef.current?.querySelectorAll("[data-motion='suggestion-item']");
    const composer = rootRef.current?.querySelector("[data-motion='command-composer']");
    const gradient = rootRef.current?.querySelector("[data-motion='overlay-gradient']");
    const scanBeam = rootRef.current?.querySelector("[data-motion='overlay-scan-beam']");
    const spark = rootRef.current?.querySelector("[data-motion='composer-spark']");
    const hiddenTargets = [
      ...(composer ? [composer] : []),
      ...(gradient ? [gradient] : []),
      ...(scanBeam ? [scanBeam] : []),
      ...(spark ? [spark] : []),
      ...Array.from(suggestions ?? [])
    ];
    const visibleTargets = [
      ...(overlay ? [overlay] : [])
    ];

    gsap.killTweensOf([...visibleTargets, ...(panel ? [panel] : []), ...hiddenTargets]);
    openTimelineRef.current?.kill();
    openTimelineRef.current = null;
    gsap.set(visibleTargets, {
      autoAlpha: 1,
      x: 0,
      y: 0,
      yPercent: 0,
      scale: 1,
      scaleY: 1,
      rotation: 0,
      clearProps: "visibility"
    });
    gsap.set(panel ?? [], {
      autoAlpha: 1,
      x: 0,
      y: 0,
      scale: 1,
      scaleY: 1,
      rotation: 0,
      clearProps: "visibility"
    });
    gsap.set(hiddenTargets, {
      autoAlpha: 0,
      x: 0,
      y: 0,
      yPercent: 0,
      scale: 1,
      scaleY: 1,
      rotation: 0
    });
  }, []);

  useGSAP(() => {
    if (isTauriRuntime()) {
      resetOverlayMotionTargets();
      return () => {
        openTimelineRef.current?.kill();
        openTimelineRef.current = null;
      };
    }
    playOverlayOpenMotion();
    return () => {
      openTimelineRef.current?.kill();
      openTimelineRef.current = null;
    };
  }, { dependencies: [playOverlayOpenMotion, resetOverlayMotionTargets], scope: rootRef });

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
    const scanBeam = rootRef.current?.querySelector("[data-motion='overlay-scan-beam']");
    const spark = rootRef.current?.querySelector("[data-motion='composer-spark']");
    const suggestionItems = Array.from(suggestions ?? []);
    const exitTargets = [
      ...(composer ? [composer] : []),
      ...(spark ? [spark] : []),
      ...suggestionItems
    ];
    const animatedTargets = [
      ...(panel ? [panel] : []),
      ...(gradient ? [gradient] : []),
      ...(scanBeam ? [scanBeam] : []),
      ...exitTargets
    ];

    openTimelineRef.current?.kill();
    openTimelineRef.current = null;
    gsap.killTweensOf(animatedTargets);

    gsap.timeline({
      defaults: { ease: "power2.inOut" },
      onComplete: () => {
        void hideCurrentWindow().then(resetOverlayMotionTargets).finally(resolve);
      }
    })
      .to(panel ?? [], {
        autoAlpha: 0,
        y: 12,
        duration: getMotionDuration(0.12, reduceMotion)
      }, 0)
      .to(exitTargets, {
        autoAlpha: 0,
        y: 18,
        scale: 0.985,
        duration: getMotionDuration(0.16, reduceMotion)
      }, 0)
      .to(gradient ?? [], {
        autoAlpha: 0,
        y: 10,
        duration: getMotionDuration(0.16, reduceMotion)
      }, 0)
      .to(scanBeam ?? [], {
        autoAlpha: 0,
        y: 14,
        duration: getMotionDuration(0.08, reduceMotion)
      }, 0)
      .to(rootRef.current, {
        autoAlpha: 0,
        duration: getMotionDuration(0.08, reduceMotion)
      }, 0.08);
  }), [reduceMotion, resetOverlayMotionTargets]);

  const { closeWindow: closeOverlayWithMotion } = useWindowLifecycle({
    onOpen: playOverlayOpenMotion,
    onClose: runCloseMotion,
    closeOnBlur: true,
    shouldIgnoreClose: (reason) => reason === "blur" && Date.now() < ignoreBlurUntilRef.current
  });

  useEffect(() => {
    const source = openEventStream(
      (event) => {
        setStreamError(null);
        addEvent(event);
      },
      () => {
        if (streamErrorTimerRef.current !== null) {
          window.clearTimeout(streamErrorTimerRef.current);
        }
        streamErrorTimerRef.current = window.setTimeout(() => {
          setStreamError("任务事件连接异常，请确认后端服务已在 127.0.0.1:8765 启动");
        }, 1500);
      },
      () => {
        if (streamErrorTimerRef.current !== null) {
          window.clearTimeout(streamErrorTimerRef.current);
          streamErrorTimerRef.current = null;
        }
        setStreamError(null);
      }
    );
    return () => {
      if (streamErrorTimerRef.current !== null) {
        window.clearTimeout(streamErrorTimerRef.current);
        streamErrorTimerRef.current = null;
      }
      source.close();
    };
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
      <div className="overlay-scan-beam" data-motion="overlay-scan-beam" />
      <section className="overlay-workspace">
        {mode !== "idle" && hasVisibleTaskSteps ? (
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
