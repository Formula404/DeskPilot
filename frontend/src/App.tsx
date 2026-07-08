import {
  ArrowUp,
  Bot,
  Check,
  Clock3,
  Copy,
  FileText,
  History,
  Info,
  Keyboard,
  LayoutGrid,
  PanelRight,
  Power,
  Settings,
  ShieldCheck,
  Sparkles,
  Square,
  User,
  X
} from "lucide-react";
import { FormEvent, MouseEvent as ReactMouseEvent, useEffect, useMemo, useRef, useState } from "react";
import { currentMonitor, LogicalPosition, LogicalSize, PhysicalPosition, Window } from "@tauri-apps/api/window";
import { cancelTask, createTask, openEventStream } from "./api/client";
import type { TaskEvent } from "./types/api";
import { useTaskStore } from "./store/taskStore";
import deskpilotWhiteIcon from "./assets/deskpilot-white.png";

type AppView = "floating-ball" | "overlay" | "settings";
type WindowView = AppView | "context-menu";
type OverlayMode = "idle" | "creating" | "running" | "completed" | "failed" | "cancelled";

interface SuggestedAction {
  id: string;
  label: string;
  prompt: string;
  icon: typeof FileText;
}

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

const settingsNav = [
  { label: "账号", icon: User },
  { label: "通用", icon: Settings },
  { label: "悬浮球", icon: PanelRight },
  { label: "快捷键", icon: Keyboard },
  { label: "上下文权限", icon: ShieldCheck },
  { label: "AI 设置", icon: Bot },
  { label: "关于", icon: Info }
];

const FLOATING_CLOSED_SIZE = 132;
const CONTEXT_MENU_WIDTH = 188;
const CONTEXT_MENU_HEIGHT = 178;
let overlayLifecycleVersion = 0;

function isTauriRuntime() {
  return "__TAURI_INTERNALS__" in window;
}

async function showWindow(label: WindowView) {
  if (!isTauriRuntime()) {
    return;
  }
  const target = await Window.getByLabel(label);
  await target?.show();
  await target?.setFocus();
}

async function hideCurrentWindow() {
  if (!isTauriRuntime()) {
    return;
  }
  const current = await Window.getCurrent();
  await current.hide();
  if (current.label === "overlay") {
    restoreFloatingBall();
  }
}

function restoreFloatingBall() {
  if (!isTauriRuntime()) {
    return;
  }
  const restoreVersion = overlayLifecycleVersion;

  async function showIfOverlayClosed() {
    const [floatingBall, overlay] = await Promise.all([
      Window.getByLabel("floating-ball"),
      Window.getByLabel("overlay")
    ]);
    const overlayVisible = overlay ? await overlay.isVisible() : false;
    if (!floatingBall || overlayVisible || restoreVersion !== overlayLifecycleVersion) {
      return;
    }
    await floatingBall.show();
    const overlayReopened = overlay ? await overlay.isVisible() : false;
    if (overlayReopened || restoreVersion !== overlayLifecycleVersion) {
      await floatingBall.hide();
    }
  }

  void showIfOverlayClosed();
  window.setTimeout(() => void showIfOverlayClosed(), 120);
  window.setTimeout(() => void showIfOverlayClosed(), 360);
}

async function showOverlayWindow() {
  if (!isTauriRuntime()) {
    return;
  }
  const overlay = await Window.getByLabel("overlay");
  if (!overlay) {
    return;
  }
  const floatingBall = await Window.getByLabel("floating-ball");
  try {
    overlayLifecycleVersion += 1;
    const monitor = await currentMonitor();
    if (monitor) {
      const position = monitor.position.toLogical(monitor.scaleFactor);
      const size = monitor.size.toLogical(monitor.scaleFactor);
      await overlay.setPosition(new LogicalPosition(position.x, position.y));
      await overlay.setSize(new LogicalSize(size.width, size.height));
    }
    await floatingBall?.hide();
    await overlay.show();
    await overlay.setFocus();
  } catch (error) {
    restoreFloatingBall();
    console.warn("Failed to show overlay window", error);
  }
}

function mapEventStatus(event: TaskEvent): "success" | "running" | "failed" | "waiting" {
  if (event.type.includes("failed")) return "failed";
  if (event.type.includes("cancelled")) return "failed";
  if (event.type.includes("completed") || event.type.includes("finished")) return "success";
  if (event.type.includes("approval") || event.type.includes("created")) return "waiting";
  return "running";
}

function useWindowView(): WindowView {
  const [view, setView] = useState<WindowView>("overlay");

  useEffect(() => {
    if (!isTauriRuntime()) {
      return;
    }
    try {
      const current = Window.getCurrent();
      const label = current.label as WindowView;
      if (label === "floating-ball" || label === "overlay" || label === "settings" || label === "context-menu") {
        setView(label);
      }
    } catch {
      setView("overlay");
    }
  }, []);

  return view;
}

export function App() {
  const view = useWindowView();

  if (view === "floating-ball") {
    return <FloatingBallView />;
  }

  if (view === "context-menu") {
    return <ContextMenuView />;
  }

  if (view === "settings") {
    return <SettingsView />;
  }

  return <OverlayView />;
}

function FloatingBallView() {
  const dragStateRef = useRef<{ startX: number; startY: number; dragging: boolean } | null>(null);

  useEffect(() => {
    void initializeFloatingWindow();
  }, []);

  async function initializeFloatingWindow() {
    if (!isTauriRuntime()) {
      return;
    }
    try {
      const current = Window.getCurrent();
      const monitor = await currentMonitor();
      await current.setSize(new LogicalSize(FLOATING_CLOSED_SIZE, FLOATING_CLOSED_SIZE));
      if (!monitor) {
        return;
      }
      const workAreaPosition = monitor.workArea.position.toLogical(monitor.scaleFactor);
      const workAreaSize = monitor.workArea.size.toLogical(monitor.scaleFactor);
      await current.setPosition(
        new LogicalPosition(
          workAreaPosition.x + workAreaSize.width - FLOATING_CLOSED_SIZE - 16,
          workAreaPosition.y + workAreaSize.height / 2 - FLOATING_CLOSED_SIZE / 2
        )
      );
    } catch (error) {
      console.warn("Failed to initialize floating window", error);
    }
  }

  async function showContextMenu() {
    if (!isTauriRuntime()) {
      return;
    }
    try {
      const current = Window.getCurrent();
      const menu = await Window.getByLabel("context-menu");
      if (!menu) {
        return;
      }
      if (await menu.isVisible()) {
        await menu.hide();
        return;
      }
      const scaleFactor = await current.scaleFactor();
      const position = await current.outerPosition();
      const monitor = await currentMonitor();
      const menuWidth = Math.round(CONTEXT_MENU_WIDTH * scaleFactor);
      const menuHeight = Math.round(CONTEXT_MENU_HEIGHT * scaleFactor);
      let nextX = position.x - Math.round((CONTEXT_MENU_WIDTH + 10) * scaleFactor);
      let nextY = position.y + Math.round(14 * scaleFactor);
      if (monitor) {
        const minX = monitor.position.x;
        const minY = monitor.position.y;
        const maxX = minX + monitor.size.width - menuWidth;
        const maxY = minY + monitor.size.height - menuHeight;
        const rightSideX = position.x + Math.round((FLOATING_CLOSED_SIZE - 30) * scaleFactor);
        nextX = nextX < minX ? rightSideX : nextX;
        nextX = Math.min(Math.max(nextX, minX), maxX);
        nextY = Math.min(Math.max(nextY, minY), maxY);
      }
      await menu.setSize(new LogicalSize(CONTEXT_MENU_WIDTH, CONTEXT_MENU_HEIGHT));
      await menu.setPosition(new PhysicalPosition(nextX, nextY));
      await menu.show();
      await menu.setFocus();
    } catch (error) {
      console.warn("Failed to show context menu", error);
    }
  }

  async function openContextMenu(event: ReactMouseEvent<HTMLButtonElement>) {
    event.preventDefault();
    event.stopPropagation();
    await showContextMenu();
  }

  function startDragging(event: ReactMouseEvent<HTMLButtonElement>) {
    if (event.button !== 0 || !isTauriRuntime()) {
      return;
    }
    event.preventDefault();
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
      void Window.getByLabel("context-menu").then((menu) => menu?.hide());
      Window.getCurrent().startDragging().catch((error) => {
        console.warn("Failed to start dragging floating window", error);
      });
      cleanup();
    }

    function onMouseUp() {
      cleanup();
    }

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  }

  async function openOverlayOnClick() {
    if (dragStateRef.current?.dragging) {
      dragStateRef.current = null;
      return;
    }
    dragStateRef.current = null;
    await Window.getByLabel("context-menu").then((menu) => menu?.hide());
    await showOverlayWindow();
  }

  return (
    <main className="floating-stage">
      <button
        className="floating-orb"
        onClick={openOverlayOnClick}
        onContextMenu={openContextMenu}
        onMouseDown={startDragging}
        title="打开 DeskPilot，拖动可移动，右键打开菜单"
      >
        <img src={deskpilotWhiteIcon} alt="" className="orb-logo" />
        <span className="status-ring" />
      </button>
    </main>
  );
}

function ContextMenuView() {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        void hideCurrentWindow();
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  async function openSettings() {
    await hideCurrentWindow();
    await showWindow("settings");
  }

  return (
    <main className="context-menu-stage" onContextMenu={(event) => event.preventDefault()}>
      <nav className="orb-menu" aria-label="悬浮球菜单">
        <button className="orb-menu-item is-active" onClick={openSettings}>
          <Settings size={17} />
          <span>设置</span>
        </button>
        <button className="orb-menu-item">
          <User size={17} />
          <span>个人信息</span>
        </button>
        <button className="orb-menu-item">
          <History size={17} />
          <span>任务历史</span>
        </button>
        <div className="orb-menu-divider" />
        <button className="orb-menu-item">
          <Power size={17} />
          <span>退出 DeskPilot</span>
        </button>
      </nav>
    </main>
  );
}

function OverlayView() {
  const [message, setMessage] = useState("");
  const [isCreatingTask, setIsCreatingTask] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
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

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        void hideCurrentWindow();
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (!isTauriRuntime()) {
      return;
    }

    let unlisten: (() => void) | undefined;
    let didCleanup = false;
    Window.getCurrent()
      .onFocusChanged(({ payload: focused }) => {
        if (!focused) {
          void hideCurrentWindow();
        }
      })
      .then((nextUnlisten) => {
        if (didCleanup) {
          nextUnlisten();
          return;
        }
        unlisten = nextUnlisten;
      })
      .catch((error) => {
        console.warn("Failed to listen overlay focus changes", error);
      });

    return () => {
      didCleanup = true;
      unlisten?.();
    };
  }, []);

  async function submitTask(nextMessage: string) {
    const trimmed = nextMessage.trim();
    if (!trimmed || isCreatingTask) {
      return;
    }
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
      }
    }
  }

  return (
    <main
      className="overlay-stage"
      onMouseDownCapture={(event) => {
        const target = event.target as HTMLElement;
        if (!target.closest("[data-overlay-interactive='true']")) {
          void hideCurrentWindow();
        }
      }}
    >
      <section className="overlay-workspace">
        {mode !== "idle" ? (
          <TaskExecutionPanel events={currentTaskEvents} mode={mode} />
        ) : null}

        <section className="composer-area">
          {actionError || streamError ? (
            <div className="overlay-status-message" data-overlay-interactive="true">
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
                  disabled={isCreatingTask}
                  onClick={() => submitTask(action.prompt)}
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
            onChange={setMessage}
            onSubmit={onSubmit}
            onStop={stopTask}
          />
        </section>
      </section>
    </main>
  );
}

function CommandComposer({
  message,
  mode,
  disabled,
  onChange,
  onSubmit,
  onStop
}: {
  message: string;
  mode: OverlayMode;
  disabled?: boolean;
  onChange: (message: string) => void;
  onSubmit: (event: FormEvent) => void;
  onStop: () => void;
}) {
  const running = mode === "running";
  const creating = mode === "creating";

  return (
    <form className="command-composer" onSubmit={onSubmit} data-overlay-interactive="true">
      <Sparkles className="composer-spark" size={28} />
      <input
        autoFocus
        disabled={disabled}
        value={message}
        onChange={(event) => onChange(event.target.value)}
        placeholder="输入你想让 DeskPilot 做的事..."
      />
      <button
        className={running ? "composer-send is-stop" : "composer-send"}
        disabled={creating || disabled}
        type={running ? "button" : "submit"}
        onClick={running ? onStop : undefined}
        title={running ? "停止任务" : creating ? "创建任务中" : "发送"}
      >
        {running ? <Square size={20} /> : creating ? <Clock3 size={22} /> : <ArrowUp size={24} />}
      </button>
    </form>
  );
}

function TaskExecutionPanel({
  events,
  mode
}: {
  events: TaskEvent[];
  mode: OverlayMode;
}) {
  const visibleEvents = events.slice(-7);
  const hiddenEventCount = Math.max(events.length - visibleEvents.length, 0);
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

  return (
    <aside className="task-side-panel" data-overlay-interactive="true">
      <div className={`task-status-pill is-${mode}`}>
        <Sparkles size={16} />
        <span>{title}</span>
      </div>

      <ol className="task-steps">
        {hiddenEventCount > 0 ? <li className="task-overflow-note">已收起 {hiddenEventCount} 条较早事件</li> : null}
        {visibleEvents.length ? visibleEvents.map((event, index) => {
          const status = mapEventStatus(event);
          const sequence = hiddenEventCount + index + 1;
          return (
            <li key={event.event_id} className={`task-step is-${status}`}>
              <span className="step-index">{status === "success" ? <Check size={14} /> : sequence}</span>
              <span className="step-message">{event.message}</span>
              <span className="step-state">{status === "running" ? "运行中" : status === "waiting" ? "待确认" : status === "failed" ? "失败" : "完成"}</span>
            </li>
          );
        }) : (
          <li className="task-empty-state">等待后端返回任务事件...</li>
        )}
      </ol>
    </aside>
  );
}

function SettingsView() {
  const [active, setActive] = useState("账号");

  return (
    <main className="settings-stage">
      <aside className="settings-sidebar">
        <div className="settings-logo">
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
                onClick={() => setActive(item.label)}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <section className="settings-content">
        <header className="settings-window-bar">
          <span>设置页面</span>
          <div className="window-dots">
            <span />
            <span />
            <button onClick={() => void hideCurrentWindow()} title="关闭">
              <X size={18} />
            </button>
          </div>
        </header>

        <div className="settings-card">
          <h1>{active}</h1>
          {active === "账号" ? <AccountSettings /> : <GenericSettings active={active} />}
        </div>
      </section>
    </main>
  );
}

function AccountSettings() {
  return (
    <div className="account-panel">
      <div className="profile-summary">
        <div className="avatar">D</div>
        <div>
          <h2>本地模式 <span>本地</span></h2>
          <p>数据仅保存在此设备</p>
        </div>
      </div>

      <div className="settings-list">
        <div className="settings-list-row">
          <User size={18} />
          <span>用户名</span>
          <strong>Demo User</strong>
        </div>
        <div className="settings-list-row">
          <Copy size={18} />
          <span>本地用户 ID</span>
          <strong>a1e4f7b2-6d9c-4f18-b8d3</strong>
        </div>
        <div className="settings-list-row">
          <Clock3 size={18} />
          <span>模型服务状态</span>
          <strong className="is-running">运行中</strong>
        </div>
      </div>
      <div className="settings-pagination">
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
  return (
    <div className="generic-settings">
      <div className="empty-setting-icon">
        <Settings size={30} />
      </div>
      <h2>{active}配置</h2>
      <p>这里用于承载 {active} 的配置项。第一版先完成页面结构，后续接入真实设置读写。</p>
      <div className="setting-toggle-row">
        <span>启用此模块</span>
        <button className="toggle is-on" aria-label="启用此模块" />
      </div>
    </div>
  );
}
