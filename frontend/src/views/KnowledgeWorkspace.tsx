import { MouseEvent as ReactMouseEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Window } from "@tauri-apps/api/window";
import {
  BookOpen,
  Check,
  ChevronRight,
  CircleAlert,
  Database,
  FileClock,
  FileText,
  FolderSearch,
  Globe2,
  LoaderCircle,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Search,
  Settings,
  ShieldCheck,
  Tag,
  Trash2,
  Upload,
  X
} from "lucide-react";
import deskpilotLogo from "../assets/deskpilot-logo.png";
import {
  compileKnowledgeSource,
  activateKnowledgeProfile,
  checkKnowledgeSourceUpdate,
  createKnowledgeProfile,
  getKnowledgeNote,
  getKnowledgeNotes,
  getKnowledgeProposal,
  getKnowledgeProposals,
  getKnowledgeProfiles,
  getKnowledgeSnapshot,
  getKnowledgeSource,
  getKnowledgeSources,
  getKnowledgeStatus,
  ingestCurrentPage,
  resolveKnowledgeProposal,
  updateKnowledgeWatch,
  uploadKnowledgeFile
  ,deleteKnowledgeNote
  ,answerKnowledge,
  promoteKnowledgeAnswer
  ,refreshKnowledgeNote
  ,updateKnowledgeNote
} from "../api/client";
import type {
  KnowledgeNoteDetail,
  KnowledgeNoteSummary,
  KnowledgeProfile,
  KnowledgeProposal,
  KnowledgeProposalDetail,
  KnowledgeSnapshotDetail,
  KnowledgeSourceDetail,
  KnowledgeSourceSummary,
  KnowledgeStatus
} from "../types/api";
import { hideCurrentWindow, isTauriRuntime, showWindow } from "./windowActions";

type WorkspaceView = "notes" | "sources" | "review" | "query";
type Notice = { tone: "success" | "error"; text: string } | null;

const entityLabels: Record<string, string> = {
  concept: "概念",
  person: "人物",
  project: "项目",
  tool: "工具",
  method: "方法",
  event: "事件",
  note: "笔记"
};

export function KnowledgeWorkspaceView() {
  const [view, setView] = useState<WorkspaceView>("notes");
  const [status, setStatus] = useState<KnowledgeStatus | null>(null);
  const [query, setQuery] = useState("");
  const [entityType, setEntityType] = useState("");
  const [noteStatus, setNoteStatus] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [notes, setNotes] = useState<KnowledgeNoteSummary[]>([]);
  const [sources, setSources] = useState<KnowledgeSourceSummary[]>([]);
  const [proposals, setProposals] = useState<KnowledgeProposal[]>([]);
  const [selectedNoteId, setSelectedNoteId] = useState<string | null>(null);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [noteDetail, setNoteDetail] = useState<KnowledgeNoteDetail | null>(null);
  const [sourceDetail, setSourceDetail] = useState<KnowledgeSourceDetail | null>(null);
  const [snapshotDetail, setSnapshotDetail] = useState<KnowledgeSnapshotDetail | null>(null);
  const [proposalDetail, setProposalDetail] = useState<KnowledgeProposalDetail | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [action, setAction] = useState<"idle" | "ingest" | "compile" | "review" | "query" | "promote" | "check" | "watch" | "refresh-note" | "edit-note" | "delete-note">("idle");
  const [queryAnswer, setQueryAnswer] = useState("");
  const [queryResults, setQueryResults] = useState<KnowledgeNoteSummary[]>([]);
  const [notice, setNotice] = useState<Notice>(null);
  const [profiles, setProfiles] = useState<KnowledgeProfile[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragRef = useRef<{ x: number; y: number; dragging: boolean } | null>(null);

  const refreshStatus = useCallback(async () => {
    setStatus(await getKnowledgeStatus());
  }, []);

  useEffect(() => {
    void Promise.all([refreshStatus(), getKnowledgeProfiles().then((value) => setProfiles(value.items))]).catch(() => setStatus(null));
  }, [refreshStatus]);

  const loadNotes = useCallback(async () => {
    const result = await getKnowledgeNotes({ query, entityType, status: noteStatus });
    setNotes(result.items);
    setSelectedNoteId((current) => result.items.some((item) => item.id === current) ? current : result.items[0]?.id ?? null);
  }, [entityType, noteStatus, query]);

  const loadSources = useCallback(async () => {
    const result = await getKnowledgeSources({ query, sourceType });
    setSources(result.items);
    setSelectedSourceId((current) => result.items.some((item) => item.id === current) ? current : result.items[0]?.id ?? null);
  }, [query, sourceType]);

  const loadProposals = useCallback(async () => {
    const items = await getKnowledgeProposals();
    const filtered = query
      ? items.filter((item) => `${item.target_title ?? ""} ${item.id} ${item.operation}`.toLowerCase().includes(query.toLowerCase()))
      : items;
    setProposals(filtered);
    setSelectedProposalId((current) => filtered.some((item) => item.id === current) ? current : filtered[0]?.id ?? null);
  }, [query]);

  useEffect(() => {
    let cancelled = false;
    const timeout = window.setTimeout(() => {
      setListLoading(true);
      const task = view === "notes" ? loadNotes() : view === "sources" ? loadSources() : view === "review" ? loadProposals() : Promise.resolve();
      void task
        .catch((error) => {
          if (!cancelled) setNotice({ tone: "error", text: error instanceof Error ? error.message : "列表读取失败" });
        })
        .finally(() => {
          if (!cancelled) setListLoading(false);
        });
    }, 180);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [loadNotes, loadProposals, loadSources, view]);

  useEffect(() => {
    if (!selectedNoteId || view !== "notes") {
      setNoteDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    void getKnowledgeNote(selectedNoteId)
      .then((value) => { if (!cancelled) setNoteDetail(value); })
      .catch((error) => { if (!cancelled) setNotice({ tone: "error", text: String(error) }); })
      .finally(() => { if (!cancelled) setDetailLoading(false); });
    return () => { cancelled = true; };
  }, [selectedNoteId, view]);

  useEffect(() => {
    if (!selectedSourceId || view !== "sources") {
      setSourceDetail(null);
      setSnapshotDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    void getKnowledgeSource(selectedSourceId)
      .then(async (value) => {
        if (cancelled) return;
        setSourceDetail(value);
        const snapshotId = value.current_snapshot_id ?? value.snapshots[0]?.id;
        setSnapshotDetail(snapshotId ? await getKnowledgeSnapshot(snapshotId) : null);
      })
      .catch((error) => { if (!cancelled) setNotice({ tone: "error", text: String(error) }); })
      .finally(() => { if (!cancelled) setDetailLoading(false); });
    return () => { cancelled = true; };
  }, [selectedSourceId, view]);

  useEffect(() => {
    if (!selectedProposalId || view !== "review") {
      setProposalDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    void getKnowledgeProposal(selectedProposalId)
      .then((value) => { if (!cancelled) setProposalDetail(value); })
      .catch((error) => { if (!cancelled) setNotice({ tone: "error", text: String(error) }); })
      .finally(() => { if (!cancelled) setDetailLoading(false); });
    return () => { cancelled = true; };
  }, [selectedProposalId, view]);

  const counts = useMemo(() => ({
    notes: status?.notes ?? 0,
    sources: status?.sources ?? 0,
    review: status?.pending_proposals ?? 0
  }), [status]);

  function switchView(next: WorkspaceView) {
    setView(next);
    setQuery("");
    setNotice(null);
  }

  async function runIngest() {
    setAction("ingest");
    setNotice(null);
    try {
      await ingestCurrentPage();
      await Promise.all([refreshStatus(), loadNotes(), loadSources()]);
      setNotice({ tone: "success", text: "当前网页已完成入库处理" });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "网页入库失败" });
    } finally {
      setAction("idle");
    }
  }

  async function switchProfile(profileId: string) {
    setListLoading(true);
    try {
      await activateKnowledgeProfile(profileId);
      setSelectedNoteId(null); setSelectedSourceId(null); setSelectedProposalId(null);
      const profileResult = await getKnowledgeProfiles();
      setProfiles(profileResult.items);
      await Promise.all([refreshStatus(), loadNotes(), loadSources(), loadProposals()]);
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "Profile 切换失败" });
    } finally { setListLoading(false); }
  }

  async function addProfile() {
    const name = window.prompt("新知识库名称");
    if (!name?.trim()) return;
    try {
      const profile = await createKnowledgeProfile(name.trim());
      await switchProfile(profile.id);
    } catch (error) { setNotice({ tone: "error", text: error instanceof Error ? error.message : "Profile 创建失败" }); }
  }

  async function importFile(file: File) {
    setAction("ingest");
    try {
      await uploadKnowledgeFile(file);
      await Promise.all([refreshStatus(), loadNotes(), loadSources()]);
      setView("sources");
      setNotice({ tone: "success", text: `${file.name} 已导入并编译` });
    } catch (error) { setNotice({ tone: "error", text: error instanceof Error ? error.message : "文件导入失败" }); }
    finally { setAction("idle"); if (fileInputRef.current) fileInputRef.current.value = ""; }
  }

  async function runCompile() {
    if (!selectedSourceId) return;
    setAction("compile");
    try {
      const result = await compileKnowledgeSource(selectedSourceId) as { pending?: unknown[] };
      await Promise.all([refreshStatus(), loadSources(), loadProposals()]);
      if (result.pending?.length) {
        setView("review");
        setNotice({ tone: "success", text: "已生成更新建议，请确认后写入知识页面" });
      } else setNotice({ tone: "success", text: "来源已重新编译，关联知识已更新" });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "来源编译失败" });
    } finally {
      setAction("idle");
    }
  }

  async function refreshStaleNote() {
    if (!noteDetail?.sources.length) return;
    setAction("refresh-note"); setNotice(null);
    try {
      const result = await refreshKnowledgeNote(noteDetail.id);
      await Promise.all([refreshStatus(), loadNotes(), loadProposals()]);
      if (result.pending.length) {
        setView("review");
        setNotice({ tone: "success", text: "更新建议已生成。请比较新旧内容后选择接受或拒绝" });
      } else {
        setNoteDetail(await getKnowledgeNote(noteDetail.id));
        setNotice({ tone: "success", text: "知识页面已根据最新来源重新生成" });
      }
    } catch (error) { setNotice({ tone: "error", text: error instanceof Error ? error.message : "知识更新失败" }); }
    finally { setAction("idle"); }
  }

  async function saveNote(payload: { title: string; entity_type: string; summary: string; overview: string; details: string; tags: string[] }) {
    if (!noteDetail) return;
    setAction("edit-note"); setNotice(null);
    try {
      const updated = await updateKnowledgeNote(noteDetail.id, payload);
      setNoteDetail(updated);
      await Promise.all([loadNotes(), refreshStatus()]);
      setNotice({ tone: "success", text: "知识页面已保存，人工修改内容将受到保护" });
    } catch (error) { setNotice({ tone: "error", text: error instanceof Error ? error.message : "知识页面保存失败" }); throw error; }
    finally { setAction("idle"); }
  }

  async function removeNote() {
    if (!noteDetail || !window.confirm(`确定删除知识页面“${noteDetail.title}”吗？\n\n页面、关系和检索索引会被删除，原始资料仍会保留。`)) return;
    setAction("delete-note"); setNotice(null);
    try {
      await deleteKnowledgeNote(noteDetail.id);
      setSelectedNoteId(null); setNoteDetail(null);
      await Promise.all([loadNotes(), loadProposals(), refreshStatus()]);
      setNotice({ tone: "success", text: "知识页面已删除，原始资料仍然保留" });
    } catch (error) { setNotice({ tone: "error", text: error instanceof Error ? error.message : "知识页面删除失败" }); }
    finally { setAction("idle"); }
  }

  async function changeWatch(enabled: boolean) {
    if (!sourceDetail) return;
    setAction("watch");
    try {
      await updateKnowledgeWatch(sourceDetail.id, enabled);
      setSourceDetail(await getKnowledgeSource(sourceDetail.id));
      setNotice({ tone: "success", text: enabled ? "自动检查已开启" : "自动检查已关闭" });
    } catch (error) { setNotice({ tone: "error", text: error instanceof Error ? error.message : "监控设置失败" }); }
    finally { setAction("idle"); }
  }

  async function checkSourceNow() {
    if (!sourceDetail) return;
    setAction("check"); setNotice(null);
    try {
      const result = await checkKnowledgeSourceUpdate(sourceDetail.id) as { check_status?: string; error?: string };
      setSourceDetail(await getKnowledgeSource(sourceDetail.id));
      await Promise.all([loadSources(), loadNotes(), loadProposals(), refreshStatus()]);
      if (result.check_status === "failed") throw new Error(result.error || "网页检查失败");
      setNotice({ tone: "success", text: result.check_status === "changed" ? "发现网页变化，已创建新快照并处理知识更新" : "检查完成，网页内容没有变化" });
    } catch (error) { setNotice({ tone: "error", text: error instanceof Error ? error.message : "网页检查失败" }); }
    finally { setAction("idle"); }
  }

  async function runQuery() {
    if (!query.trim()) return;
    setAction("query");
    try {
      const result = await answerKnowledge(query.trim());
      setQueryAnswer(result.answer);
      setQueryResults(result.results);
    } catch (error) { setNotice({ tone: "error", text: error instanceof Error ? error.message : "知识查询失败" }); }
    finally { setAction("idle"); }
  }

  async function promoteQuery() {
    if (!queryAnswer || !queryResults.length) return;
    const title = window.prompt("知识页面标题", query.trim());
    if (!title?.trim()) return;
    setAction("promote");
    try {
      const note = await promoteKnowledgeAnswer(title.trim(), queryAnswer, queryResults.map((item) => item.id));
      await Promise.all([refreshStatus(), loadNotes()]);
      setNotice({ tone: "success", text: `回答已沉淀为「${note.title}」` });
    } catch (error) { setNotice({ tone: "error", text: error instanceof Error ? error.message : "回答沉淀失败" }); }
    finally { setAction("idle"); }
  }

  async function resolveProposal(decision: "accept" | "reject") {
    if (!selectedProposalId) return;
    setAction("review");
    try {
      const result = await resolveKnowledgeProposal(selectedProposalId, decision) as { note?: { note_id?: string; id?: string } };
      await Promise.all([refreshStatus(), loadProposals(), loadNotes()]);
      if (decision === "accept") {
        const noteId = result.note?.note_id || result.note?.id || proposalDetail?.target_note_id;
        if (noteId) {
          setSelectedNoteId(noteId);
          setNoteDetail(await getKnowledgeNote(noteId));
          setView("notes");
        }
      }
      setNotice({ tone: "success", text: decision === "accept" ? "修改已写入知识页面" : "提案已拒绝" });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "提案处理失败" });
    } finally {
      setAction("idle");
    }
  }

  function startWindowDrag(event: ReactMouseEvent<HTMLElement>) {
    if (event.button !== 0 || !isTauriRuntime()) return;
    if ((event.target as HTMLElement).closest("button, input, select, a, [data-no-window-drag]")) return;
    dragRef.current = { x: event.screenX, y: event.screenY, dragging: false };
    function cleanup() {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    }
    function move(next: MouseEvent) {
      const state = dragRef.current;
      if (!state || state.dragging || Math.hypot(next.screenX - state.x, next.screenY - state.y) < 4) return;
      state.dragging = true;
      void Window.getCurrent().startDragging();
      cleanup();
    }
    function up() { dragRef.current = null; cleanup(); }
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }

  return (
    <main className="knowledge-workspace" onMouseDown={startWindowDrag}>
      <aside className="knowledge-workspace-sidebar">
        <div className="knowledge-workspace-brand"><img src={deskpilotLogo} alt="DeskPilot" /></div>
        <div className="knowledge-profile-control" data-no-window-drag>
          <select value={status?.active_profile_id ?? "profile_default"} onChange={(event) => void switchProfile(event.target.value)} aria-label="当前知识库">
            {profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
          </select>
          <button onClick={() => void addProfile()} title="新建知识库"><Plus size={15} /></button>
        </div>
        <nav aria-label="知识库视图" data-no-window-drag>
          <WorkspaceNav icon={BookOpen} label="知识页面" count={counts.notes} active={view === "notes"} onClick={() => switchView("notes")} />
          <WorkspaceNav icon={Database} label="原始资料" count={counts.sources} active={view === "sources"} onClick={() => switchView("sources")} />
          <WorkspaceNav icon={ShieldCheck} label="需要确认" count={counts.review} active={view === "review"} onClick={() => switchView("review")} />
          <WorkspaceNav icon={Search} label="问知识库" count={queryResults.length} active={view === "query"} onClick={() => switchView("query")} />
        </nav>
        <div className="knowledge-workspace-sidebar-footer">
          <button onClick={() => void showWindow("settings")} title="设置"><Settings size={17} /><span>设置</span></button>
          <span className={status?.enabled ? "workspace-service-dot is-online" : "workspace-service-dot"} />
        </div>
      </aside>

      <section className="knowledge-browser-panel">
        <header className="knowledge-workspace-titlebar">
          <div><strong>{view === "notes" ? "知识页面" : view === "sources" ? "原始资料" : view === "review" ? "需要确认" : "问知识库"}</strong><span>{view === "notes" ? "阅读整理后的结论" : view === "sources" ? "管理网页和导入文件" : view === "review" ? "确认 AI 提议的修改" : "查询并沉淀新知识"}</span></div>
          <div className="knowledge-window-actions" data-no-window-drag>
            <input ref={fileInputRef} type="file" hidden accept=".md,.txt,.pdf,.docx,image/*" onChange={(event) => { const file = event.target.files?.[0]; if (file) void importFile(file); }} />
            <button onClick={() => fileInputRef.current?.click()} disabled={action !== "idle"} title="导入 PDF、DOCX、图片或文本"><Upload size={16} /></button>
            <button onClick={() => void runIngest()} disabled={action !== "idle" || !status?.browser_connected} title="收录当前页">
              {action === "ingest" ? <LoaderCircle className="is-spinning" size={16} /> : <Globe2 size={16} />}
            </button>
            <button onClick={() => void hideCurrentWindow()} title="关闭"><X size={17} /></button>
          </div>
        </header>

        <div className="knowledge-search-row" data-no-window-drag>
          <Search size={16} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && view === "query") void runQuery(); }} placeholder={view === "query" ? "向知识库提问" : "搜索标题、来源或提案"} />
          {query ? <button onClick={() => setQuery("")} title="清除搜索"><X size={14} /></button> : null}
        </div>

        <div className="knowledge-filter-row" data-no-window-drag>
          {view === "query" ? <button className="workspace-query-button" onClick={() => void runQuery()} disabled={action !== "idle" || !query.trim()}>{action === "query" ? "检索中" : "查询 Wiki"}</button> : view === "notes" ? <>
            <select value={entityType} onChange={(event) => setEntityType(event.target.value)} aria-label="知识类型">
              <option value="">全部类型</option>
              {Object.entries(entityLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
            <select value={noteStatus} onChange={(event) => setNoteStatus(event.target.value)} aria-label="知识状态">
              <option value="">全部状态</option><option value="active">已同步</option><option value="stale">需要更新</option><option value="draft">草稿</option>
            </select>
            {(status?.stale_notes ?? 0) > 0 && noteStatus !== "stale" ? <button className="knowledge-stale-filter-button" onClick={() => setNoteStatus("stale")}><RefreshCw size={13} />{status?.stale_notes} 个页面需要更新</button> : null}
          </> : view === "sources" ?
            <select value={sourceType} onChange={(event) => setSourceType(event.target.value)} aria-label="来源类型">
              <option value="">全部来源</option><option value="web">网页</option><option value="file">文件</option><option value="user">文本</option>
            </select> : <span>这里列出 AI 对现有知识提出的修改，接受后才会写入</span>}
        </div>

        <div className="knowledge-item-list" data-no-window-drag>
          {listLoading ? <LoadingState label="正在读取" /> : view === "notes" ? (
            notes.length ? notes.map((item) => <NoteListItem key={item.id} item={item} active={item.id === selectedNoteId} onClick={() => setSelectedNoteId(item.id)} />) : <EmptyState label="没有匹配的知识条目" />
          ) : view === "sources" ? (
            sources.length ? sources.map((item) => <SourceListItem key={item.id} item={item} active={item.id === selectedSourceId} onClick={() => setSelectedSourceId(item.id)} />) : <EmptyState label="没有匹配的来源" />
          ) : view === "review" ? (proposals.length ? proposals.map((item) => <ProposalListItem key={item.id} item={item} active={item.id === selectedProposalId} onClick={() => setSelectedProposalId(item.id)} />) : <EmptyState label="当前没有待审提案" />) : queryResults.length ? queryResults.map((item) => <NoteListItem key={item.id} item={item} active={false} onClick={() => { setView("notes"); setSelectedNoteId(item.id); }} />) : <EmptyState label="输入问题并查询 Wiki" />}
        </div>
      </section>

      <section className="knowledge-detail-panel" data-no-window-drag>
        {notice ? <div className={`workspace-notice is-${notice.tone}`}><CircleAlert size={15} /><span>{notice.text}</span><button onClick={() => setNotice(null)}><X size={13} /></button></div> : null}
        {detailLoading ? <LoadingState label="正在读取详情" /> : view === "notes" ? (
          noteDetail ? <NoteDetail detail={noteDetail} action={action} onRefresh={() => void refreshStaleNote()} onSave={saveNote} onDelete={() => void removeNote()} onOpenSource={(id) => { setView("sources"); setSelectedSourceId(id); setQuery(""); }} onOpenNote={setSelectedNoteId} /> : <EmptyDetail />
        ) : view === "sources" ? (
          sourceDetail ? <SourceDetail detail={sourceDetail} snapshot={snapshotDetail} action={action} onCompile={() => void runCompile()} onSnapshot={async (id) => setSnapshotDetail(await getKnowledgeSnapshot(id))} onWatch={(enabled) => void changeWatch(enabled)} onCheck={() => void checkSourceNow()} /> : <EmptyDetail />
        ) : view === "review" && proposalDetail ? (
          <ProposalDetail detail={proposalDetail} action={action} onResolve={(decision) => void resolveProposal(decision)} />
        ) : view === "query" && queryAnswer ? <article className="knowledge-document"><header><div className="knowledge-document-kicker"><span>Wiki 综合回答</span></div><h1>{query}</h1></header><div className="knowledge-markdown-text">{queryAnswer}</div><div className="knowledge-review-actions"><button className="is-accept" disabled={action !== "idle" || !queryResults.length} onClick={() => void promoteQuery()}><Plus size={16} />沉淀为知识页面</button></div></article> : <EmptyDetail />}
      </section>
    </main>
  );
}

function WorkspaceNav({ icon: Icon, label, count, active, onClick }: { icon: typeof BookOpen; label: string; count: number; active: boolean; onClick: () => void }) {
  return <button className={active ? "is-active" : ""} onClick={onClick}><Icon size={18} /><span>{label}</span><small>{count}</small></button>;
}

function NoteListItem({ item, active, onClick }: { item: KnowledgeNoteSummary; active: boolean; onClick: () => void }) {
  return <button className={active ? "knowledge-list-item is-active" : "knowledge-list-item"} onClick={onClick}>
    <span className="knowledge-list-icon"><FileText size={16} /></span><span className="knowledge-list-copy"><strong>{item.title}</strong><small>{entityLabels[item.entity_type] ?? item.entity_type} · {formatDate(item.updated_at)}</small></span><StatusBadge status={item.status} />
  </button>;
}

function SourceListItem({ item, active, onClick }: { item: KnowledgeSourceSummary; active: boolean; onClick: () => void }) {
  return <button className={active ? "knowledge-list-item is-active" : "knowledge-list-item"} onClick={onClick}>
    <span className="knowledge-list-icon">{item.source_type === "web" ? <Globe2 size={16} /> : <FileText size={16} />}</span><span className="knowledge-list-copy"><strong>{item.title}</strong><small>{item.snapshot_count} 个快照 · {item.note_count} 条知识</small></span><StatusBadge status={item.status} />
  </button>;
}

function ProposalListItem({ item, active, onClick }: { item: KnowledgeProposal; active: boolean; onClick: () => void }) {
  return <button className={active ? "knowledge-list-item is-active" : "knowledge-list-item"} onClick={onClick}>
    <span className="knowledge-list-icon"><FileClock size={16} /></span><span className="knowledge-list-copy"><strong>{item.target_title || "新知识条目"}</strong><small>{operationLabel(item.operation)} · {formatDate(item.created_at)}</small></span><ChevronRight size={15} />
  </button>;
}

function NoteDetail({ detail, action, onRefresh, onSave, onDelete, onOpenSource, onOpenNote }: { detail: KnowledgeNoteDetail; action: string; onRefresh: () => void; onSave: (payload: { title: string; entity_type: string; summary: string; overview: string; details: string; tags: string[] }) => Promise<void>; onDelete: () => void; onOpenSource: (id: string) => void; onOpenNote: (id: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ title: detail.title, entity_type: detail.entity_type, summary: detail.sections.Summary || "", overview: detail.sections.Overview || "", details: detail.sections.Details || "", tags: (detail.frontmatter.tags || []).join(", ") });
  useEffect(() => {
    setDraft({ title: detail.title, entity_type: detail.entity_type, summary: detail.sections.Summary || "", overview: detail.sections.Overview || "", details: detail.sections.Details || "", tags: (detail.frontmatter.tags || []).join(", ") });
    setEditing(false);
  }, [detail.id, detail.updated_at]);
  if (editing) return <article className="knowledge-document">
    <header className="knowledge-note-manage-header"><div><div className="knowledge-document-kicker"><span>编辑知识页面</span></div><h1>{detail.title}</h1></div><button className="knowledge-icon-button" title="取消编辑" onClick={() => setEditing(false)} disabled={action !== "idle"}><X size={17} /></button></header>
    <form className="knowledge-note-editor" onSubmit={(event) => { event.preventDefault(); void onSave({ ...draft, title: draft.title.trim(), tags: draft.tags.split(/[,，]/).map((item) => item.trim()).filter(Boolean) }).then(() => setEditing(false)).catch(() => undefined); }}>
      <label><span>标题</span><input value={draft.title} required maxLength={300} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
      <label><span>页面类型</span><select value={draft.entity_type} onChange={(event) => setDraft({ ...draft, entity_type: event.target.value })}>{["concept", "method", "tool", "project", "person", "event", "note"].map((value) => <option key={value} value={value}>{entityLabels[value] ?? value}</option>)}</select></label>
      <label><span>标签</span><input value={draft.tags} placeholder="多个标签用逗号分隔" onChange={(event) => setDraft({ ...draft, tags: event.target.value })} /></label>
      <label><span>摘要</span><textarea rows={4} value={draft.summary} onChange={(event) => setDraft({ ...draft, summary: event.target.value })} /></label>
      <label><span>概览</span><textarea rows={8} value={draft.overview} onChange={(event) => setDraft({ ...draft, overview: event.target.value })} /></label>
      <label><span>详情</span><textarea rows={18} value={draft.details} onChange={(event) => setDraft({ ...draft, details: event.target.value })} /></label>
      <div className="knowledge-note-editor-actions"><button type="button" onClick={() => setEditing(false)} disabled={action !== "idle"}>取消</button><button className="is-primary" type="submit" disabled={action !== "idle" || !draft.title.trim()}>{action === "edit-note" ? <LoaderCircle className="is-spinning" size={16} /> : <Save size={16} />}{action === "edit-note" ? "正在保存" : "保存修改"}</button></div>
    </form>
  </article>;
  return <article className="knowledge-document">
    <header className="knowledge-note-manage-header"><div><div className="knowledge-document-kicker"><span>{entityLabels[detail.entity_type] ?? detail.entity_type}</span><StatusBadge status={detail.status} /></div><h1>{detail.title}</h1><p className="knowledge-document-meta">更新于 {formatDate(detail.updated_at)} · {detail.markdown_path}</p></div><div className="knowledge-note-manage-actions"><button className="knowledge-icon-button" title="编辑知识页面" onClick={() => setEditing(true)} disabled={action !== "idle"}><Pencil size={17} /></button><button className="knowledge-icon-button is-danger" title="删除知识页面" onClick={onDelete} disabled={action !== "idle"}>{action === "delete-note" ? <LoaderCircle className="is-spinning" size={17} /> : <Trash2 size={17} />}</button></div></header>
    {detail.status === "stale" ? <section className="knowledge-action-callout is-warning"><div><CircleAlert size={18} /><span><strong>原始资料已有新版本</strong><small>当前页面仍是旧结论。重新生成后，如果修改了已有内容，会先交给你确认。</small></span></div><button onClick={onRefresh} disabled={action !== "idle"}>{action === "refresh-note" ? <LoaderCircle className="is-spinning" size={16} /> : <RefreshCw size={16} />}{action === "refresh-note" ? "正在生成" : "根据最新资料更新"}</button></section> : <section className="knowledge-sync-state"><Check size={15} /><span>已与当前原始资料同步</span></section>}
    {detail.frontmatter.tags?.length ? <div className="knowledge-tag-row"><Tag size={14} />{detail.frontmatter.tags.map((tag) => <span key={tag}>{tag}</span>)}</div> : null}
    <DocumentSection title="摘要" content={detail.sections.Summary} prominent />
    <DocumentSection title="概览" content={detail.sections.Overview} />
    <DocumentSection title="详情" content={detail.sections.Details} />
    <section className="knowledge-document-section"><h2>来源证据</h2>{detail.sources.length ? <div className="knowledge-link-list">{detail.sources.map((source) => <button key={`${source.source_id}-${source.evidence_anchor}`} onClick={() => onOpenSource(source.source_id)}><Globe2 size={15} /><span><strong>{source.source_title}</strong><small>{source.evidence_anchor || "来源"}</small></span><ChevronRight size={15} /></button>)}</div> : <p className="knowledge-muted">暂无来源证据</p>}</section>
    <section className="knowledge-document-section"><h2>关系</h2>{detail.relations.length ? <div className="knowledge-link-list">{detail.relations.map((relation) => <button key={relation.id} onClick={() => onOpenNote(relation.to_note_id)}><BookOpen size={15} /><span><strong>{relation.target_title}</strong><small>{relation.relation_type}</small></span><ChevronRight size={15} /></button>)}</div> : <p className="knowledge-muted">暂无关联条目</p>}</section>
  </article>;
}

function SourceDetail({ detail, snapshot, action, onCompile, onSnapshot, onWatch, onCheck }: { detail: KnowledgeSourceDetail; snapshot: KnowledgeSnapshotDetail | null; action: string; onCompile: () => void; onSnapshot: (id: string) => void; onWatch: (enabled: boolean) => void; onCheck: () => void }) {
  const watchEnabled = Boolean(detail.watch?.enabled);
  return <article className="knowledge-document">
    <header className="knowledge-source-header"><div><div className="knowledge-document-kicker"><span>{sourceTypeLabel(detail.source_type)}</span><StatusBadge status={detail.status} /></div><h1>{detail.title}</h1><p className="knowledge-document-meta">{detail.canonical_uri || detail.id}</p></div><button className="workspace-command-button" onClick={onCompile} disabled={action !== "idle"}>{action === "compile" ? <LoaderCircle className="is-spinning" size={15} /> : <RefreshCw size={15} />}{action === "compile" ? "正在生成" : "重新生成知识"}</button></header>
    <div className="knowledge-source-facts"><span><strong>{detail.snapshots.length}</strong>快照</span><span><strong>{detail.sensitivity}</strong>敏感级别</span><span><strong>{formatDate(detail.updated_at)}</strong>最近更新</span></div>
    <section className="knowledge-purpose-strip"><strong>原始资料有什么用？</strong><span>它是知识页面的证据。网页或文件变化时会保留新快照，再用它重新生成相关知识。</span></section>
    {detail.source_type === "web" ? <section className="knowledge-monitor-panel"><div className="knowledge-monitor-heading"><div><FileClock size={17} /><span><strong>网页变化监控</strong><small>{watchEnabled ? `已开启 · 每 ${intervalLabel(detail.watch?.interval_minutes)}检查` : "未开启自动检查"}</small></span></div><button className={watchEnabled ? "knowledge-toggle is-on" : "knowledge-toggle"} role="switch" aria-checked={watchEnabled} disabled={action !== "idle"} onClick={() => onWatch(!watchEnabled)}><span /></button></div><div className="knowledge-monitor-status"><span><small>上次检查</small><strong>{formatDate(detail.watch?.last_checked_at)}</strong></span><span><small>检查结果</small><strong className={`is-${detail.watch?.last_status ?? "never"}`}>{watchStatusLabel(detail.watch?.last_status)}</strong></span><span><small>下次检查</small><strong>{watchEnabled ? formatDate(detail.watch?.next_check_at) : "未安排"}</strong></span></div>{detail.watch?.last_error ? <p className="knowledge-monitor-error">{detail.watch.last_error}</p> : null}<button className="knowledge-check-button" onClick={onCheck} disabled={action !== "idle"}>{action === "check" ? <LoaderCircle className="is-spinning" size={15} /> : <RefreshCw size={15} />}{action === "check" ? "正在访问网页并比较内容" : "立即检查网页是否变化"}</button></section> : null}
    <section className="knowledge-document-section"><h2>资料版本</h2><p className="knowledge-section-help">每次内容变化都会保存一个快照，旧版本不会被覆盖。</p><div className="knowledge-snapshot-tabs">{detail.snapshots.map((item) => <button key={item.id} className={snapshot?.id === item.id ? "is-active" : ""} onClick={() => onSnapshot(item.id)}>{formatDate(item.captured_at)}{item.id === detail.current_snapshot_id ? <span>最新</span> : null}</button>)}</div></section>
    {snapshot ? <><DocumentSection title="来源正文" content={snapshot.sections.Content?.replace(/<!--\s*chunk:chunk-\d+\s*-->\s*/g, "")} /><section className="knowledge-document-section"><h2>快照信息</h2><dl className="knowledge-definition-list"><div><dt>快照 ID</dt><dd>{snapshot.id}</dd></div><div><dt>内容哈希</dt><dd>{snapshot.content_sha256}</dd></div><div><dt>文件</dt><dd>{snapshot.markdown_path}</dd></div></dl></section></> : null}
  </article>;
}

function ProposalDetail({ detail, action, onResolve }: { detail: KnowledgeProposalDetail; action: string; onResolve: (decision: "accept" | "reject") => void }) {
  const operation = detail.payload?.operation;
  return <article className="knowledge-document">
    <header><div className="knowledge-document-kicker"><span>需要你的确认</span><span className="knowledge-badge is-pending">未处理</span></div><h1>{operation?.title || detail.target_title || "知识变更"}</h1><p className="knowledge-document-meta">{detail.id} · {operationLabel(detail.operation)}</p></header>
    <section className="knowledge-purpose-strip"><strong>为什么需要确认？</strong><span>AI 建议修改已有知识。接受会把右侧内容写入知识库；拒绝会保留当前版本。</span></section>
    <div className="knowledge-review-actions"><button className="is-accept" disabled={action !== "idle"} onClick={() => onResolve("accept")}>{action === "review" ? <LoaderCircle className="is-spinning" size={16} /> : <Check size={16} />}接受修改</button><button className="is-reject" disabled={action !== "idle"} onClick={() => onResolve("reject")}><X size={16} />保留当前版本</button></div>
    <div className="knowledge-diff-grid"><section><h2>当前内容</h2><DiffField label="摘要" value={detail.target_note?.sections.Summary} empty="新建条目" /><DiffField label="概览" value={detail.target_note?.sections.Overview} /></section><section className="is-proposed"><h2>提议内容</h2><DiffField label="摘要" value={operation?.summary} /><DiffField label="概览" value={operation?.overview} /><DiffField label="详情" value={operation?.details_markdown} /></section></div>
  </article>;
}

function DocumentSection({ title, content, prominent = false }: { title: string; content?: string; prominent?: boolean }) {
  if (!content) return null;
  return <section className={prominent ? "knowledge-document-section is-prominent" : "knowledge-document-section"}><h2>{title}</h2><div className="knowledge-markdown-text">{content}</div></section>;
}

function DiffField({ label, value, empty = "无内容" }: { label: string; value?: string; empty?: string }) {
  return <div className="knowledge-diff-field"><strong>{label}</strong><div>{value || empty}</div></div>;
}

function StatusBadge({ status }: { status: string }) { return <span className={`knowledge-badge is-${status}`}>{statusLabel(status)}</span>; }
function LoadingState({ label }: { label: string }) { return <div className="knowledge-panel-state"><LoaderCircle className="is-spinning" size={20} /><span>{label}</span></div>; }
function EmptyState({ label }: { label: string }) { return <div className="knowledge-panel-state"><FolderSearch size={22} /><span>{label}</span></div>; }
function EmptyDetail() { return <div className="knowledge-empty-detail"><BookOpen size={28} /><span>选择一项查看详情</span></div>; }
function statusLabel(status: string) { return ({ active: "已同步", stale: "需要更新", draft: "草稿", updated: "有新版本", captured: "已采集", archived: "已归档" } as Record<string, string>)[status] ?? status; }
function sourceTypeLabel(value: string) { return ({ web: "网页资料", file: "导入文件", user: "用户文本" } as Record<string, string>)[value] ?? value; }
function watchStatusLabel(value?: string | null) { return ({ changed: "发现变化", unchanged: "没有变化", failed: "检查失败" } as Record<string, string>)[value ?? ""] ?? "尚未检查"; }
function intervalLabel(value?: number | null) { if (!value) return "24 小时"; if (value < 60) return `${value} 分钟`; if (value % 1440 === 0) return `${value / 1440} 天`; return `${value / 60} 小时`; }
function operationLabel(value: string) { return ({ create_note: "新建条目", update_note: "更新条目", add_relation: "新增关系", mark_conflict: "标记冲突" } as Record<string, string>)[value] ?? value; }
function formatDate(value?: string | null) { if (!value) return "未知"; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date); }
