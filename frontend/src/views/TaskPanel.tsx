import { useMemo, useRef } from "react";
import { Check, Sparkles, Wrench } from "lucide-react";
import type { TaskEvent } from "../types/api";
import type { OverlayMode } from "../types/window";
import { gsap, useGSAP } from "../motion/register";
import { getMotionDuration, motion } from "../motion/constants";
import { useReducedMotion } from "../motion/useReducedMotion";
import { isVisibleTaskStep, mapEventStatus } from "./taskStatus";

function stepToolName(event: TaskEvent) {
  const step = event.payload?.step;
  if (!step || typeof step !== "object" || !("type" in step) || !("name" in step)) {
    return null;
  }
  const typedStep = step as { type?: unknown; name?: unknown };
  if (typedStep.type !== "tool" || typeof typedStep.name !== "string") {
    return null;
  }
  return typedStep.name;
}
export function TaskExecutionPanel({
  events,
  mode
}: {
  events: TaskEvent[];
  mode: OverlayMode;
}) {
  const rootRef = useRef<HTMLElement | null>(null);
  const stepLoopRef = useRef<Map<string, gsap.core.Timeline>>(new Map());
  const previousCountRef = useRef(0);
  const reduceMotion = useReducedMotion();
  const executionEvents = useMemo(() => events.filter(isVisibleTaskStep), [events]);
  const visibleEvents = useMemo(() => executionEvents.slice(-5), [executionEvents]);
  const hiddenEventCount = Math.max(executionEvents.length - visibleEvents.length, 0);
  const eventStatusSignature = useMemo(
    () => visibleEvents.reduce((signature, event) => `${signature};${event.event_id}:${mapEventStatus(event)}`, `${visibleEvents.length}`),
    [visibleEvents]
  );
  const title =
    mode === "creating"
      ? "正在创建任务"
      : mode === "completed"
        ? "任务已完成"
        : mode === "failed"
          ? "任务执行失败"
          : mode === "cancelled"
            ? "任务已取消"
          : "任务执行";

  useGSAP(() => {
    const panel = rootRef.current?.querySelector("[data-motion='task-panel']");
    const pill = rootRef.current?.querySelector("[data-motion='task-status-pill']");
    const steps = rootRef.current?.querySelectorAll("[data-motion='task-step']");
    if (!panel) {
      return;
    }

    gsap.timeline({ defaults: { ease: motion.ease.out } })
      .fromTo(panel, {
        autoAlpha: 0,
        x: 24
      }, {
        autoAlpha: 1,
        x: 0,
        duration: getMotionDuration(0.22, reduceMotion)
      })
      .from(pill ?? [], {
        autoAlpha: 0,
        y: -6,
        duration: getMotionDuration(0.16, reduceMotion)
      }, "<0.04")
      .from(steps ?? [], {
        autoAlpha: 0,
        y: 8,
        stagger: reduceMotion ? 0 : motion.stagger.normal,
        duration: getMotionDuration(0.16, reduceMotion)
      }, "<0.04");
  }, { dependencies: [reduceMotion], scope: rootRef });

  useGSAP(() => {
    const nextCount = visibleEvents.length;
    const added = nextCount > previousCountRef.current;
    previousCountRef.current = nextCount;

    if (!added) {
      return;
    }

    const taskItems = rootRef.current?.querySelectorAll(".task-step[data-motion='task-step']");
    const latest = taskItems?.[taskItems.length - 1];
    const index = latest?.querySelector("[data-motion='step-index']");
    const message = latest?.querySelector("[data-motion='step-message']");
    const state = latest?.querySelector("[data-motion='step-state']");
    if (!latest) {
      return;
    }

    gsap.timeline({ defaults: { ease: motion.ease.out } })
      .fromTo(latest, {
        autoAlpha: 0,
        y: 10,
        scale: 0.985
      }, {
        autoAlpha: 1,
        y: 0,
        scale: 1,
        duration: getMotionDuration(motion.duration.base, reduceMotion)
      })
      .from(index ?? [], { scale: 0.7, duration: getMotionDuration(0.14, reduceMotion) }, "<0.03")
      .from(message ?? [], { autoAlpha: 0, x: -4, duration: getMotionDuration(0.14, reduceMotion) }, "<0.03")
      .from(state ?? [], { autoAlpha: 0, x: 4, duration: getMotionDuration(0.12, reduceMotion) }, "<0.04");
  }, { dependencies: [visibleEvents.length, reduceMotion], scope: rootRef });

  useGSAP(() => {
    stepLoopRef.current.forEach((timeline) => timeline.kill());
    stepLoopRef.current.clear();

    if (reduceMotion) {
      return;
    }

    visibleEvents.forEach((event) => {
      const status = mapEventStatus(event);
      const step = rootRef.current?.querySelector(`[data-event-id='${event.event_id}']`);
      const index = step?.querySelector("[data-motion='step-index']");
      if (!index) {
        return;
      }

      if (status === "running") {
        stepLoopRef.current.set(event.event_id, gsap.timeline({ repeat: -1 })
          .to(index, { rotation: 360, duration: 0.9, ease: motion.ease.none }));
      }

      if (status === "waiting") {
        stepLoopRef.current.set(event.event_id, gsap.timeline({ repeat: -1, yoyo: true })
          .to(index, { scale: 1.12, autoAlpha: 0.76, duration: 0.6, ease: "sine.inOut" }));
      }
    });

    return () => {
      stepLoopRef.current.forEach((timeline) => timeline.kill());
      stepLoopRef.current.clear();
    };
  }, { dependencies: [eventStatusSignature, reduceMotion], scope: rootRef });

  useGSAP(() => {
    const pill = rootRef.current?.querySelector("[data-motion='task-status-pill']");
    const sweep = rootRef.current?.querySelector("[data-motion='status-sweep']");
    if (!pill) {
      return;
    }

    if (mode === "running" && sweep && !reduceMotion) {
      const sweepTl = gsap.timeline({ repeat: -1, repeatDelay: 0.4 })
        .fromTo(sweep, { xPercent: -120, autoAlpha: 0 }, { xPercent: -80, autoAlpha: 1, duration: 0.08 })
        .to(sweep, { xPercent: 120, duration: 0.7, ease: "power1.inOut" })
        .to(sweep, { autoAlpha: 0, duration: 0.08 });
      return () => sweepTl.kill();
    }

    if (mode === "completed") {
      stepLoopRef.current.forEach((timeline) => timeline.kill());
      gsap.set(pill, { clearProps: "transform" });
    }

    if (mode === "failed" || mode === "cancelled") {
      stepLoopRef.current.forEach((timeline) => timeline.kill());
      gsap.set(pill, { clearProps: "transform" });
    }
  }, { dependencies: [mode, reduceMotion], scope: rootRef });

  return (
    <aside ref={rootRef} className="task-side-panel" data-overlay-interactive="true">
      <div className="task-panel-content" data-motion="task-panel">
        <div className={`task-status-pill is-${mode}`} data-motion="task-status-pill">
          <span className="status-sweep" data-motion="status-sweep" />
          <Sparkles size={16} />
          <span>{title}</span>
        </div>

        <ol className="task-steps" data-motion="task-steps">
          {visibleEvents.length ? visibleEvents.map((event, index) => {
            const status = mapEventStatus(event);
            const sequence = hiddenEventCount + index + 1;
            return (
              <li key={event.event_id} className={`task-step is-${status}`} data-motion="task-step" data-event-id={event.event_id}>
                <span className="step-index" data-motion="step-index">{status === "success" ? <Check size={14} /> : stepToolName(event) ? <Wrench size={13} /> : sequence}</span>
                <span className="step-message" data-motion="step-message" title={stepToolName(event) ?? event.message}>
                  {event.message}
                  {stepToolName(event) ? <span className="step-tool-name">{stepToolName(event)}</span> : null}
                </span>
                <span className="step-state" data-motion="step-state">{status === "running" ? "运行中" : status === "waiting" ? "待确认" : status === "failed" ? "失败" : status === "cancelled" ? "已取消" : "完成"}</span>
              </li>
            );
          }) : (
            <li className="task-empty-state" data-motion="task-step">等待真实执行步骤...</li>
          )}
          {hiddenEventCount > 0 ? (
            <li className="task-overflow-note" data-motion="task-step">已收起 {hiddenEventCount} 条较早事件</li>
          ) : null}
        </ol>
      </div>
    </aside>
  );
}
