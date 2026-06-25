import { Send, Settings, Square } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { createTask, openEventStream } from "./api/client";
import { useTaskStore } from "./store/taskStore";

export function App() {
  const [message, setMessage] = useState("总结当前网页并保存");
  const { events, addEvent, currentTaskId, setCurrentTaskId } = useTaskStore();

  useEffect(() => {
    const source = openEventStream((event) => addEvent(event));
    return () => source.close();
  }, [addEvent]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const response = await createTask(message);
    setCurrentTaskId(response.task_id);
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex min-h-screen max-w-3xl flex-col gap-4 p-4">
        <header className="flex items-center justify-between border-b border-border pb-3">
          <div>
            <h1 className="text-lg font-semibold">DeskPilot</h1>
            <p className="text-sm text-muted">桌面悬浮助手骨架</p>
          </div>
          <button className="icon-button" title="设置">
            <Settings size={18} />
          </button>
        </header>

        <section className="rounded-md border border-border bg-panel p-3">
          <form className="flex gap-2" onSubmit={onSubmit}>
            <input
              className="min-w-0 flex-1 rounded-md border border-border px-3 py-2 text-sm outline-none focus:border-accent"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
            />
            <button className="primary-button" type="submit" title="发送">
              <Send size={18} />
            </button>
            <button className="icon-button" type="button" title="停止">
              <Square size={18} />
            </button>
          </form>
        </section>

        <section className="min-h-72 rounded-md border border-border bg-panel p-3">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-medium">任务事件</h2>
            <span className="text-xs text-muted">{currentTaskId ?? "未开始"}</span>
          </div>
          <div className="space-y-2">
            {events.map((event) => (
              <div key={event.event_id} className="rounded border border-border px-3 py-2 text-sm">
                <div className="font-medium">{event.message}</div>
                <div className="text-xs text-muted">{event.type}</div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
