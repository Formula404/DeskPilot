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
  Plus,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Tag,
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

type WorkspaceView = "notes" | "sources" | "review";
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
  const [action, setAction] = useState<"idle" | "ingest" | "compile" | "review">("idle");
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
      const task = view === "notes" ? loadNotes() : view === "sources" ? loadSources() : loadProposals();
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
      await compileKnowledgeSource(selectedSourceId);
      await Promise.all([refreshStatus(), loadSources(), loadProposals()]);
      setNotice({ tone: "success", text: "来源编译已完成" });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "来源编译失败" });
    } finally {
      setAction("idle");
    }
  }

  async function resolveProposal(decision: "accept" | "reject") {
    if (!selectedProposalId) return;
    setAction("review");
    try {
      await resolveKnowledgeProposal(selectedProposalId, decision);
      await Promise.all([refreshStatus(), loadProposals(), loadNotes()]);
      setNotice({ tone: "success", text: decision === "accept" ? "提案已接受" : "提案已拒绝" });
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
          <WorkspaceNav icon={BookOpen} label="知识" count={counts.notes} active={view === "notes"} onClick={() => switchView("notes")} />
          <WorkspaceNav icon={Database} label="来源" count={counts.sources} active={view === "sources"} onClick={() => switchView("sources")} />
          <WorkspaceNav icon={ShieldCheck} label="待审" count={counts.review} active={view === "review"} onClick={() => switchView("review")} />
        </nav>
        <div className="knowledge-workspace-sidebar-footer">
          <button onClick={() => void showWindow("settings")} title="设置"><Settings size={17} /><span>设置</span></button>
          <span className={status?.enabled ? "workspace-service-dot is-online" : "workspace-service-dot"} />
        </div>
      </aside>

      <section className="knowledge-browser-panel">
        <header className="knowledge-workspace-titlebar">
          <div><strong>知识库</strong><span>{view === "notes" ? "知识条目" : view === "sources" ? "来源档案" : "变更审核"}</span></div>
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
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索标题、来源或提案" />
          {query ? <button onClick={() => setQuery("")} title="清除搜索"><X size={14} /></button> : null}
        </div>

        <div className="knowledge-filter-row" data-no-window-drag>
          {view === "notes" ? <>
            <select value={entityType} onChange={(event) => setEntityType(event.target.value)} aria-label="知识类型">
              <option value="">全部类型</option>
              {Object.entries(entityLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
            <select value={noteStatus} onChange={(event) => setNoteStatus(event.target.value)} aria-label="知识状态">
              <option value="">全部状态</option><option value="active">有效</option><option value="stale">待更新</option><option value="draft">草稿</option>
            </select>
          </> : view === "sources" ?
            <select value={sourceType} onChange={(event) => setSourceType(event.target.value)} aria-label="来源类型">
              <option value="">全部来源</option><option value="web">网页</option><option value="file">文件</option><option value="user">文本</option>
            </select> : <span>等待处理的知识变更</span>}
        </div>

        <div className="knowledge-item-list" data-no-window-drag>
          {listLoading ? <LoadingState label="正在读取" /> : view === "notes" ? (
            notes.length ? notes.map((item) => <NoteListItem key={item.id} item={item} active={item.id === selectedNoteId} onClick={() => setSelectedNoteId(item.id)} />) : <EmptyState label="没有匹配的知识条目" />
          ) : view === "sources" ? (
            sources.length ? sources.map((item) => <SourceListItem key={item.id} item={item} active={item.id === selectedSourceId} onClick={() => setSelectedSourceId(item.id)} />) : <EmptyState label="没有匹配的来源" />
          ) : proposals.length ? proposals.map((item) => <ProposalListItem key={item.id} item={item} active={item.id === selectedProposalId} onClick={() => setSelectedProposalId(item.id)} />) : <EmptyState label="当前没有待审提案" />}
        </div>
      </section>

      <section className="knowledge-detail-panel" data-no-window-drag>
        {notice ? <div className={`workspace-notice is-${notice.tone}`}><CircleAlert size={15} /><span>{notice.text}</span><button onClick={() => setNotice(null)}><X size={13} /></button></div> : null}
        {detailLoading ? <LoadingState label="正在读取详情" /> : view === "notes" ? (
          noteDetail ? <NoteDetail detail={noteDetail} onOpenSource={(id) => { setView("sources"); setSelectedSourceId(id); setQuery(""); }} onOpenNote={setSelectedNoteId} /> : <EmptyDetail />
        ) : view === "sources" ? (
          sourceDetail ? <SourceDetail detail={sourceDetail} snapshot={snapshotDetail} action={action} onCompile={() => void runCompile()} onSnapshot={async (id) => setSnapshotDetail(await getKnowledgeSnapshot(id))} onWatch={async (enabled) => { await updateKnowledgeWatch(sourceDetail.id, enabled); setNotice({ tone: "success", text: enabled ? "已启用网页更新检查" : "已停用网页更新检查" }); }} onCheck={async () => { await checkKnowledgeSourceUpdate(sourceDetail.id); await Promise.all([loadSources(), refreshStatus()]); setNotice({ tone: "success", text: "网页更新检查完成" }); }} /> : <EmptyDetail />
        ) : proposalDetail ? (
          <ProposalDetail detail={proposalDetail} action={action} onResolve={(decision) => void resolveProposal(decision)} />
        ) : <EmptyDetail />}
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

function NoteDetail({ detail, onOpenSource, onOpenNote }: { detail: KnowledgeNoteDetail; onOpenSource: (id: string) => void; onOpenNote: (id: string) => void }) {
  return <article className="knowledge-document">
    <header><div className="knowledge-document-kicker"><span>{entityLabels[detail.entity_type] ?? detail.entity_type}</span><StatusBadge status={detail.status} /></div><h1>{detail.title}</h1><p className="knowledge-document-meta">更新于 {formatDate(detail.updated_at)} · {detail.markdown_path}</p></header>
    {detail.frontmatter.tags?.length ? <div className="knowledge-tag-row"><Tag size={14} />{detail.frontmatter.tags.map((tag) => <span key={tag}>{tag}</span>)}</div> : null}
    <DocumentSection title="摘要" content={detail.sections.Summary} prominent />
    <DocumentSection title="概览" content={detail.sections.Overview} />
    <DocumentSection title="详情" content={detail.sections.Details} />
    <section className="knowledge-document-section"><h2>来源证据</h2>{detail.sources.length ? <div className="knowledge-link-list">{detail.sources.map((source) => <button key={`${source.source_id}-${source.evidence_anchor}`} onClick={() => onOpenSource(source.source_id)}><Globe2 size={15} /><span><strong>{source.source_title}</strong><small>{source.evidence_anchor || "来源"}</small></span><ChevronRight size={15} /></button>)}</div> : <p className="knowledge-muted">暂无来源证据</p>}</section>
    <section className="knowledge-document-section"><h2>关系</h2>{detail.relations.length ? <div className="knowledge-link-list">{detail.relations.map((relation) => <button key={relation.id} onClick={() => onOpenNote(relation.to_note_id)}><BookOpen size={15} /><span><strong>{relation.target_title}</strong><small>{relation.relation_type}</small></span><ChevronRight size={15} /></button>)}</div> : <p className="knowledge-muted">暂无关联条目</p>}</section>
  </article>;
}

function SourceDetail({ detail, snapshot, action, onCompile, onSnapshot, onWatch, onCheck }: { detail: KnowledgeSourceDetail; snapshot: KnowledgeSnapshotDetail | null; action: string; onCompile: () => void; onSnapshot: (id: string) => void; onWatch: (enabled: boolean) => void; onCheck: () => void }) {
  return <article className="knowledge-document">
    <header className="knowledge-source-header"><div><div className="knowledge-document-kicker"><span>{detail.source_type}</span><StatusBadge status={detail.status} /></div><h1>{detail.title}</h1><p className="knowledge-document-meta">{detail.canonical_uri || detail.id}</p></div><button className="workspace-command-button" onClick={onCompile} disabled={action !== "idle"}>{action === "compile" ? <LoaderCircle className="is-spinning" size={15} /> : <RefreshCw size={15} />}编译来源</button></header>
    <div className="knowledge-source-facts"><span><strong>{detail.snapshots.length}</strong>快照</span><span><strong>{detail.sensitivity}</strong>敏感级别</span><span><strong>{formatDate(detail.updated_at)}</strong>最近更新</span></div>
    {detail.source_type === "web" ? <div className="knowledge-source-commands"><button onClick={() => onWatch(true)}><FileClock size={15} />定时检查</button><button onClick={onCheck}><RefreshCw size={15} />立即检查</button></div> : null}
    <section className="knowledge-document-section"><h2>快照历史</h2><div className="knowledge-snapshot-tabs">{detail.snapshots.map((item) => <button key={item.id} className={snapshot?.id === item.id ? "is-active" : ""} onClick={() => onSnapshot(item.id)}>{formatDate(item.captured_at)}{item.id === detail.current_snapshot_id ? <span>当前</span> : null}</button>)}</div></section>
    {snapshot ? <><DocumentSection title="来源正文" content={snapshot.sections.Content?.replace(/<!--\s*chunk:chunk-\d+\s*-->\s*/g, "")} /><section className="knowledge-document-section"><h2>快照信息</h2><dl className="knowledge-definition-list"><div><dt>快照 ID</dt><dd>{snapshot.id}</dd></div><div><dt>内容哈希</dt><dd>{snapshot.content_sha256}</dd></div><div><dt>文件</dt><dd>{snapshot.markdown_path}</dd></div></dl></section></> : null}
  </article>;
}

function ProposalDetail({ detail, action, onResolve }: { detail: KnowledgeProposalDetail; action: string; onResolve: (decision: "accept" | "reject") => void }) {
  const operation = detail.payload?.operation;
  return <article className="knowledge-document">
    <header><div className="knowledge-document-kicker"><span>待审提案</span><span className="knowledge-badge is-pending">pending</span></div><h1>{operation?.title || detail.target_title || "知识变更"}</h1><p className="knowledge-document-meta">{detail.id} · {operationLabel(detail.operation)}</p></header>
    <div className="knowledge-review-actions"><button className="is-accept" disabled={action !== "idle"} onClick={() => onResolve("accept")}><Check size={16} />接受</button><button className="is-reject" disabled={action !== "idle"} onClick={() => onResolve("reject")}><X size={16} />拒绝</button></div>
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
function statusLabel(status: string) { return ({ active: "有效", stale: "待更新", draft: "草稿", updated: "已更新", captured: "已采集", archived: "已归档" } as Record<string, string>)[status] ?? status; }
function operationLabel(value: string) { return ({ create_note: "新建条目", update_note: "更新条目", add_relation: "新增关系", mark_conflict: "标记冲突" } as Record<string, string>)[value] ?? value; }
function formatDate(value?: string | null) { if (!value) return "未知"; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date); }
