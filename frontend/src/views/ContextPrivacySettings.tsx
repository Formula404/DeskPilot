import { useCallback, useEffect, useState } from "react";
import { Database, LoaderCircle, RefreshCw, Trash2 } from "lucide-react";
import {
  deleteContextSnapshot,
  deleteMemory,
  deleteSession,
  getContextData,
  getMemories
} from "../api/client";
import type { ContextDataOverview, MemoryOverview } from "../types/api";


export function ContextPrivacySettingsPanel() {
  const [contextData, setContextData] = useState<ContextDataOverview | null>(null);
  const [memories, setMemories] = useState<MemoryOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [nextContext, nextMemories] = await Promise.all([getContextData(), getMemories()]);
      setContextData(nextContext);
      setMemories(nextMemories);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { void reload(); }, [reload]);

  async function remove(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      setBusy(false);
    }
  }

  if (!contextData || !memories) {
    return <div className="application-settings-loading"><LoaderCircle className="spin" size={22} /> 正在读取上下文数据…</div>;
  }

  return (
    <div className="application-settings">
      <div className="settings-section-heading" data-motion="settings-page-item">
        <div><h2>上下文与记忆</h2><p>查看并删除本机保存的会话、短期环境快照和长期记忆。</p></div>
        <button className="secondary-action" disabled={busy} onClick={() => void reload()}><RefreshCw size={15} />刷新</button>
      </div>
      {error ? <div className="settings-feedback is-error">{error}</div> : null}
      <div className="settings-list">
        <div className="settings-list-row" data-motion="settings-page-item">
          <Database size={18} /><span>数据概览</span>
          <strong>{contextData.counts.sessions} 个会话 · {contextData.counts.snapshots} 个快照 · {memories.items.length} 条记忆</strong>
        </div>
        {memories.items.slice(0, 20).map((memory) => (
          <div className="settings-list-row" data-motion="settings-page-item" key={memory.id}>
            <Database size={18} /><span>{memory.content}</span><strong>{memory.kind}</strong>
            <button className="secondary-action" disabled={busy} title="删除记忆" onClick={() => void remove(() => deleteMemory(memory.id))}><Trash2 size={14} /></button>
          </div>
        ))}
        {contextData.snapshots.slice(0, 20).map((snapshot) => (
          <div className="settings-list-row" data-motion="settings-page-item" key={snapshot.id}>
            <Database size={18} /><span>{snapshot.browser.title || snapshot.browser.url || "桌面上下文快照"}</span><strong>短期快照</strong>
            <button className="secondary-action" disabled={busy} title="删除快照" onClick={() => void remove(() => deleteContextSnapshot(snapshot.id))}><Trash2 size={14} /></button>
          </div>
        ))}
        {contextData.sessions.slice(0, 20).map((session) => (
          <div className="settings-list-row" data-motion="settings-page-item" key={session.id}>
            <Database size={18} /><span>{session.title || `会话 ${session.id.slice(0, 8)}`}</span><strong>{session.status}</strong>
            <button className="secondary-action" disabled={busy} title="删除会话及消息" onClick={() => void remove(() => deleteSession(session.id))}><Trash2 size={14} /></button>
          </div>
        ))}
      </div>
    </div>
  );
}
