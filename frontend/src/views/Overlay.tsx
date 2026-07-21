import { FormEvent, MouseEvent as ReactMouseEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Window } from "@tauri-apps/api/window";
import {
  BookOpen,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleStop,
  CircleX,
  Copy,
  FileText,
  Globe2,
  LayoutGrid,
  LoaderCircle,
  Minus,
  Sparkles,
  X
} from "lucide-react";
import deskpilotWhiteIcon from "../assets/deskpilot-white.png";
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
import {
  hideCurrentWindow,
  isTauriRuntime,
  setOverlayWindowShape,
  type OverlayShape
} from "./windowActions";

const suggestedActions: SuggestedAction[] = [
  { id: "summarize", label: "总结网页", prompt: "总结当前网页并保存为 Markdown", icon: FileText },
  { id: "table", label: "提取表格", prompt: "提取当前网页中的表格并保存为 Excel", icon: LayoutGrid },
  { id: "markdown", label: "保存笔记", prompt: "把当前网页整理成 Markdown 笔记", icon: Copy },
  { id: "translate", label: "翻译页面", prompt: "翻译当前页面的主要内容", icon: Bot }
];

function extractFinalResponse(events: TaskEvent[]) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const step = events[index].payload?.step;
    if (!step || typeof step !== "object" || !("output" in step)) continue;
    const output = (step as { output?: unknown }).output;
    if (!output || typeof output !== "object" || !("final_response" in output)) continue;
    const response = (output as { final_response?: unknown }).final_response;
    if (typeof response === "string" && response.trim()) return response.trim();
  }
  return "";
}

function latestStepLabel(events: TaskEvent[]) {
  const visible = events.filter(isVisibleTaskStep);
  return visible[visible.length - 1]?.message ?? "正在准备任务";
}

export function OverlayView() {
  const rootRef = useRef<HTMLElement | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);
  const openTimelineRef = useRef<gsap.core.Timeline | null>(null);
  const streamErrorTimerRef = useRef<number | null>(null);
  const [shape, setShape] = useState<OverlayShape>("quick");
  const [message, setMessage] = useState("");
  const [lastUserMessage, setLastUserMessage] = useState("");
  const [isCreatingTask, setIsCreatingTask] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [stepsExpanded, setStepsExpanded] = useState(true);
  const [composerSignal, setComposerSignal] = useState<"idle" | "submit" | "error">("idle");
  const reduceMotion = useReducedMotion();
  const { events, addEvent, clearEvents, currentTaskId, setCurrentTaskId } = useTaskStore();
  const currentTaskEvents = useMemo(
    () => events.filter((event) => !currentTaskId || event.task_id === currentTaskId || event.task_id === null),
    [currentTaskId, events]
  );
  const visibleStepCount = useMemo(
    () => currentTaskEvents.filter(isVisibleTaskStep).length,
    [currentTaskEvents]
  );
  const finalResponse = useMemo(() => extractFinalResponse(currentTaskEvents), [currentTaskEvents]);
  const mode = useMemo<OverlayMode>(() => {
    if (isCreatingTask) return "creating";
    if (currentTaskEvents.some((event) => event.type === "task.failed")) return "failed";
    if (currentTaskEvents.some((event) => event.type === "task.cancelled")) return "cancelled";
    if (currentTaskEvents.some((event) => event.type === "task.completed")) return "completed";
    if (currentTaskId) return "running";
    return "idle";
  }, [currentTaskEvents, currentTaskId, isCreatingTask]);
  const running = mode === "running" || mode === "creating";

  const playOpenMotion = useCallback(() => {
    const panel = panelRef.current;
    if (!panel || openTimelineRef.current?.isActive()) return;
    const children = panel.querySelectorAll("[data-motion='panel-item']");
    gsap.killTweensOf([panel, ...Array.from(children)]);
    openTimelineRef.current?.kill();
    openTimelineRef.current = gsap.timeline({
      defaults: { ease: motion.ease.out },
      onComplete: () => {
        openTimelineRef.current = null;
      }
    })
      .fromTo(panel, {
        autoAlpha: 0,
        y: 12,
        scale: 0.965,
        transformOrigin: "right bottom"
      }, {
        autoAlpha: 1,
        y: 0,
        scale: 1,
        duration: getMotionDuration(0.22, reduceMotion)
      })
      .from(children, {
        autoAlpha: 0,
        y: 5,
        duration: getMotionDuration(0.16, reduceMotion),
        stagger: reduceMotion ? 0 : 0.025
      }, "<0.05");
  }, [reduceMotion]);

  useGSAP(() => {
    if (isTauriRuntime()) {
      gsap.set(panelRef.current, {
        autoAlpha: 0,
        y: 12,
        scale: 0.965,
        transformOrigin: "50% 100%"
      });
      return () => openTimelineRef.current?.kill();
    }
    playOpenMotion();
    return () => openTimelineRef.current?.kill();
  }, { dependencies: [playOpenMotion], scope: rootRef });

  useEffect(() => {
    if (!isTauriRuntime()) return;
    let unlisten: (() => void) | undefined;
    let disposed = false;
    Window.getCurrent().listen("overlay-open-request", () => {
      setShape("quick");
      window.requestAnimationFrame(() => playOpenMotion());
    }).then((nextUnlisten) => {
      if (disposed) {
        nextUnlisten();
      } else {
        unlisten = nextUnlisten;
      }
    }).catch((error) => {
      console.warn("Failed to listen for overlay open requests", error);
    });
    return () => {
      disposed = true;
      unlisten?.();
    };
  }, [playOpenMotion]);

  useGSAP(() => {
    const content = shape === "hud"
      ? panelRef.current?.querySelectorAll(".assistant-hud-state, .assistant-hud-copy, .assistant-hud-actions")
      : panelRef.current?.querySelector(".assistant-quick-body, .assistant-conversation");
    if (!content || (content instanceof NodeList && !content.length)) return;
    gsap.fromTo(content, {
      autoAlpha: 0.7,
      y: shape === "conversation" ? 6 : -3
    }, {
      autoAlpha: 1,
      y: 0,
      duration: getMotionDuration(0.16, reduceMotion),
      ease: "power3.out",
      immediateRender: false,
      clearProps: "transform,opacity,visibility"
    });
  }, { dependencies: [shape, reduceMotion], scope: rootRef });

  useEffect(() => {
    void setOverlayWindowShape(shape).catch((error) => {
      console.warn("Failed to resize overlay window", error);
    });
  }, [shape]);

  const runCloseMotion = useCallback(() => new Promise<void>((resolve) => {
    openTimelineRef.current?.kill();
    openTimelineRef.current = null;
    gsap.to(panelRef.current, {
      autoAlpha: 0,
      y: 8,
      scale: 0.97,
      duration: getMotionDuration(0.14, reduceMotion),
      ease: "power2.in",
      onComplete: () => {
        setShape("quick");
        void hideCurrentWindow().finally(resolve);
      }
    });
  }), [reduceMotion]);

  const ensureOpenMotion = useCallback(() => {
    const panel = panelRef.current;
    if (!panel || openTimelineRef.current?.isActive()) return;
    const opacity = Number(gsap.getProperty(panel, "opacity"));
    if (opacity < 0.05 || window.getComputedStyle(panel).visibility === "hidden") {
      playOpenMotion();
    }
  }, [playOpenMotion]);

  const { closeWindow } = useWindowLifecycle({
    onOpen: ensureOpenMotion,
    onClose: runCloseMotion,
    closeOnBlur: false,
    replayOnFocus: true
  });

  useEffect(() => {
    const source = openEventStream(
      (event) => {
        setStreamError(null);
        addEvent(event);
      },
      () => {
        if (streamErrorTimerRef.current !== null) window.clearTimeout(streamErrorTimerRef.current);
        streamErrorTimerRef.current = window.setTimeout(() => {
          setStreamError("任务事件连接异常，请确认本地服务已启动");
        }, 1500);
      },
      () => {
        if (streamErrorTimerRef.current !== null) window.clearTimeout(streamErrorTimerRef.current);
        streamErrorTimerRef.current = null;
        setStreamError(null);
      }
    );
    return () => {
      if (streamErrorTimerRef.current !== null) window.clearTimeout(streamErrorTimerRef.current);
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
    setLastUserMessage(trimmed);
    setShape("conversation");
    setStepsExpanded(true);
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
    if (!currentTaskId) return;
    setActionError(null);
    try {
      await cancelTask(currentTaskId);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "停止任务失败");
    }
  }

  function animateSuggestion(event: ReactMouseEvent<HTMLButtonElement>, hovered: boolean) {
    gsap.to(event.currentTarget, {
      y: hovered ? -2 : 0,
      scale: hovered ? 1.012 : 1,
      duration: motion.duration.fast,
      ease: motion.ease.out,
      overwrite: "auto"
    });
  }

  function startNewConversation() {
    setMessage("");
    setLastUserMessage("");
    setActionError(null);
    setStreamError(null);
    clearEvents();
    setCurrentTaskId(null);
    setShape("quick");
  }

  const statusLabel = mode === "completed"
    ? "任务已完成"
    : mode === "failed"
      ? "任务执行失败"
      : mode === "cancelled"
        ? "任务已取消"
        : latestStepLabel(currentTaskEvents);

  if (shape === "hud") {
    return (
      <main ref={rootRef} className="overlay-stage overlay-stage-hud">
        <section ref={panelRef} className={`assistant-hud is-${mode}`} data-motion="assistant-panel">
          <span className="assistant-hud-state">
            {running
              ? <LoaderCircle className="assistant-spin" size={18} />
              : mode === "failed"
                ? <CircleX size={18} />
                : mode === "cancelled"
                  ? <CircleStop size={18} />
                  : <CheckCircle2 size={18} />}
          </span>
          <span className="assistant-hud-copy">
            <strong>{running ? "DeskPilot 正在执行" : statusLabel}</strong>
            <small>{statusLabel}{visibleStepCount ? ` · ${visibleStepCount} 个步骤` : ""}</small>
          </span>
          <span className="assistant-hud-actions">
            <button onClick={() => setShape("conversation")} title="展开对话"><ChevronUp size={17} /></button>
            {running ? <button className="is-danger" onClick={stopTask} title="停止任务"><CircleStop size={17} /></button> : null}
            <button onClick={() => void closeWindow()} title="关闭"><X size={17} /></button>
          </span>
        </section>
      </main>
    );
  }

  return (
    <main ref={rootRef} className={`overlay-stage overlay-stage-${shape}`}>
      <section ref={panelRef} className={`assistant-panel is-${shape}`} data-motion="assistant-panel">
        <header className="assistant-titlebar" data-tauri-drag-region data-motion="panel-item">
          <span className="assistant-brand" data-tauri-drag-region>
            <span className="assistant-brand-mark"><img src={deskpilotWhiteIcon} alt="" /></span>
            <span data-tauri-drag-region>
              <strong>DeskPilot</strong>
            </span>
          </span>
          <span className="assistant-window-actions">
            {shape === "conversation" ? (
              <button onClick={() => setShape(running ? "hud" : "quick")} title={running ? "收起为执行控制条" : "收起"}>
                <Minus size={17} />
              </button>
            ) : null}
            <button onClick={() => void closeWindow()} title="关闭"><X size={17} /></button>
          </span>
        </header>

        {shape === "quick" ? (
          <div className="assistant-quick-body">
            <div className="assistant-suggestions" data-motion="panel-item">
              {suggestedActions.map((action) => {
                const Icon = action.icon;
                return (
                  <button
                    key={action.id}
                    className={`assistant-suggestion is-${action.id}`}
                    disabled={isCreatingTask}
                    onClick={() => void submitTask(action.prompt)}
                    onPointerEnter={(event) => animateSuggestion(event, true)}
                    onPointerLeave={(event) => animateSuggestion(event, false)}
                  >
                    <Icon size={14} />
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
          </div>
        ) : (
          <div className="assistant-conversation">
            <div className="assistant-context-row" data-motion="panel-item">
              <span><Globe2 size={13} />当前网页</span>
              <span><BookOpen size={13} />知识库</span>
              <button onClick={startNewConversation}>新对话</button>
            </div>

            <div className="assistant-messages" data-motion="panel-item">
              {lastUserMessage ? <div className="assistant-user-message">{lastUserMessage}</div> : null}

              {running ? (
                <div className="assistant-response is-running">
                  <span className="assistant-avatar"><Sparkles size={16} /></span>
                  <div>
                    <strong>正在处理</strong>
                    <p>{statusLabel}</p>
                  </div>
                </div>
              ) : finalResponse ? (
                <div className="assistant-response">
                  <span className="assistant-avatar"><Sparkles size={16} /></span>
                  <div>
                    <strong>DeskPilot</strong>
                    <p>{finalResponse}</p>
                  </div>
                </div>
              ) : null}

              {actionError || streamError ? (
                <div className="assistant-error" role="status">{actionError ?? streamError}</div>
              ) : null}

              {mode !== "idle" && visibleStepCount > 0 ? (
                <section className="assistant-execution">
                  <button className="assistant-execution-toggle" onClick={() => setStepsExpanded((value) => !value)}>
                    <span>{running ? <LoaderCircle className="assistant-spin" size={14} /> : <CheckCircle2 size={14} />}</span>
                    <strong>{running ? "执行过程" : "执行记录"}</strong>
                    <small>{visibleStepCount} 个步骤</small>
                    {stepsExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                  </button>
                  {stepsExpanded ? <TaskExecutionPanel events={currentTaskEvents} mode={mode} /> : null}
                </section>
              ) : null}
            </div>

            <footer className="assistant-composer-footer" data-motion="panel-item">
              <CommandComposer
                message={message}
                mode={mode}
                disabled={isCreatingTask}
                signal={composerSignal}
                onChange={setMessage}
                onSubmit={onSubmit}
                onStop={stopTask}
              />
            </footer>
          </div>
        )}
      </section>
    </main>
  );
}
