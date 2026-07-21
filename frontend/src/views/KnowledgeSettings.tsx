import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  BookOpenCheck,
  CheckCircle2,
  Database,
  FileCheck2,
  FileClock,
  FolderOpen,
  Network,
  Globe2,
  LoaderCircle,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  Workflow,
  X
} from "lucide-react";
import {
  getKnowledgeSettings,
  changeKnowledgeStorage,
  chooseKnowledgeStorage,
  exportObsidianVault,
  getKnowledgeStatus,
  getKnowledgeProposals,
  ingestCurrentPage,
  lintKnowledge,
  rebuildKnowledgeIndex,
  openKnowledgeStorage,
  resolveKnowledgeProposal,
  updateKnowledgeSettings
  ,semanticLintKnowledge
} from "../api/client";
import type { KnowledgeProposal, KnowledgeSettings, KnowledgeStatus } from "../types/api";

type ActionState = "idle" | "saving" | "ingesting" | "linting" | "semantic-linting" | "rebuilding" | "reviewing" | "exporting" | "relocating";

const defaultSettings: KnowledgeSettings = {
  enabled: true,
  auto_compile: true,
  review_updates: true,
  allow_private_remote: false,
  max_search_results: 8,
  auto_create_notes: true,
  web_update_enabled: false,
  web_update_interval_minutes: 1440,
  auto_watch_web_sources: false,
  obsidian_enabled: false,
  obsidian_include_sources: true,
  purpose: "",
  root_path: "",
  active_profile_id: "profile_default"
};

export function KnowledgeSettingsPanel() {
  const [settings, setSettings] = useState<KnowledgeSettings>(defaultSettings);
  const [status, setStatus] = useState<KnowledgeStatus | null>(null);
  const [proposals, setProposals] = useState<KnowledgeProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<ActionState>("idle");
  const [storagePath, setStoragePath] = useState("");
  const [notice, setNotice] = useState<{ tone: "success" | "warning" | "error"; text: string } | null>(null);

  const refresh = useCallback(async () => {
    const [settingsResult, statusResult, proposalsResult] = await Promise.allSettled([
      getKnowledgeSettings(),
      getKnowledgeStatus(),
      getKnowledgeProposals()
    ]);
    const failures: string[] = [];
    if (settingsResult.status === "fulfilled") {
      setSettings(settingsResult.value);
      setStoragePath(settingsResult.value.root_path);
    } else {
      failures.push("设置");
    }
    if (statusResult.status === "fulfilled") {
      setStatus(statusResult.value);
    } else {
      failures.push("状态");
    }
    if (proposalsResult.status === "fulfilled") {
      setProposals(proposalsResult.value);
    } else {
      failures.push("待审提案");
    }
    if (failures.length === 3) {
      throw new Error("知识库服务不可用");
    }
    if (failures.length > 0) {
      setNotice({ tone: "warning", text: `${failures.join("、")}暂时无法读取，其余数据已保留` });
    }
  }, []);

  useEffect(() => {
    void refresh()
      .catch((error) => setNotice({ tone: "error", text: error instanceof Error ? error.message : "知识库服务不可用" }))
      .finally(() => setLoading(false));
  }, [refresh]);

  async function runAction(nextAction: ActionState, task: () => Promise<unknown>, success: string) {
    setAction(nextAction);
    setNotice(null);
    try {
      await task();
      await refresh();
      setNotice({ tone: "success", text: success });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "操作失败" });
    } finally {
      setAction("idle");
    }
  }

  async function runSemanticLint() {
    setAction("semantic-linting"); setNotice(null);
    try {
      const result = await semanticLintKnowledge() as { summary?: { issues?: number }; model_used?: boolean };
      const count = result.summary?.issues ?? 0;
      setNotice({ tone: count ? "warning" : "success", text: `语义检查完成：${count} 项维护建议${result.model_used ? "（模型分析）" : "（本地规则）"}` });
    } catch (error) { setNotice({ tone: "error", text: error instanceof Error ? error.message : "语义检查失败" }); }
    finally { setAction("idle"); }
  }

  function setValue<K extends keyof KnowledgeSettings>(key: K, value: KnowledgeSettings[K]) {
    setSettings((current) => ({ ...current, [key]: value }));
  }

  if (loading) {
    return (
      <div className="knowledge-loading" data-motion="settings-page-item">
        <LoaderCircle className="is-spinning" size={22} />
        <span>正在读取知识库状态</span>
      </div>
    );
  }

  const busy = action !== "idle";
  return (
    <div className="knowledge-settings" data-motion="settings-page-item">
      <div className="knowledge-toolbar">
        <div>
          <div className="knowledge-title-row">
            <BookOpenCheck size={20} />
            <strong>本地知识编译库</strong>
            <span className={status?.browser_connected ? "service-state is-online" : "service-state"}>
              {status?.browser_connected ? "网页通道已连接" : "网页通道未连接"}
            </span>
          </div>
          <p>Markdown 保存正文，SQLite 维护索引与审计。</p>
        </div>
        <button
          className="knowledge-primary-action"
          disabled={busy || !status?.browser_connected}
          onClick={() => void runAction("ingesting", ingestCurrentPage, "当前网页已完成入库处理")}
        >
          {action === "ingesting" ? <LoaderCircle className="is-spinning" size={16} /> : <Globe2 size={16} />}
          收录当前页
        </button>
      </div>

      <div className="knowledge-metrics" aria-label="知识库统计">
        <Metric label="知识条目" value={status?.notes ?? 0} icon={Database} />
        <Metric label="来源快照" value={status?.snapshots ?? 0} icon={FileCheck2} />
        <Metric label="待审提案" value={status?.pending_proposals ?? 0} icon={ShieldCheck} />
        <Metric label="待更新" value={status?.stale_notes ?? 0} icon={RefreshCw} />
      </div>

      {notice ? (
        <div className={`knowledge-notice is-${notice.tone}`} role="status">
          {notice.tone === "success" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
          <span>{notice.text}</span>
        </div>
      ) : null}

      {proposals.length > 0 ? (
        <section className="knowledge-setting-section knowledge-proposals">
          <div className="knowledge-section-heading">
            <ShieldCheck size={18} />
            <div><strong>待审提案</strong><span>确认对已有知识的更新</span></div>
          </div>
          {proposals.slice(0, 4).map((proposal) => (
            <div className="knowledge-proposal-row" key={proposal.id}>
              <span>
                <strong>{proposal.target_title || "新知识条目"}</strong>
                <small>{proposal.id} · {proposal.operation}</small>
              </span>
              <div>
                <button
                  title="接受提案"
                  aria-label={`接受提案 ${proposal.id}`}
                  disabled={busy}
                  onClick={() => void runAction("reviewing", () => resolveKnowledgeProposal(proposal.id, "accept"), "知识提案已接受")}
                ><CheckCircle2 size={16} /></button>
                <button
                  title="拒绝提案"
                  aria-label={`拒绝提案 ${proposal.id}`}
                  disabled={busy}
                  onClick={() => void runAction("reviewing", () => resolveKnowledgeProposal(proposal.id, "reject"), "知识提案已拒绝")}
                ><X size={16} /></button>
              </div>
            </div>
          ))}
        </section>
      ) : null}

      <section className="knowledge-setting-section">
        <div className="knowledge-section-heading">
          <Network size={18} />
          <div><strong>Obsidian</strong><span>为当前 Profile 生成可独立浏览的 Vault</span></div>
        </div>
        <SettingToggle label="启用 Obsidian 集成" detail="DeskPilot 仍是知识正文的事实来源" checked={settings.obsidian_enabled} onChange={(value) => setValue("obsidian_enabled", value)} />
        <SettingToggle label="导出来源快照" detail="在 Vault 的 Sources 目录保留当前来源版本" checked={settings.obsidian_include_sources} onChange={(value) => setValue("obsidian_include_sources", value)} />
        <div className="knowledge-maintenance-actions">
          <button disabled={busy || !settings.obsidian_enabled} onClick={() => void runAction("exporting", exportObsidianVault, "Obsidian Vault 已更新")}>{action === "exporting" ? <LoaderCircle className="is-spinning" size={16} /> : <Network size={16} />}导出 Vault</button>
        </div>
      </section>

      <section className="knowledge-setting-section">
        <div className="knowledge-section-heading">
          <Workflow size={18} />
          <div><strong>编译流程</strong><span>控制来源进入知识库后的处理方式</span></div>
        </div>
        <SettingToggle
          label="启用知识库"
          detail="允许 Agent 检索和写入知识内容"
          checked={settings.enabled}
          onChange={(value) => setValue("enabled", value)}
        />
        <SettingToggle
          label="入库后自动编译"
          detail="生成知识条目或待审提案"
          checked={settings.auto_compile}
          onChange={(value) => setValue("auto_compile", value)}
        />
        <SettingToggle
          label="自动创建新条目"
          detail="来源明确的新主题可直接提交"
          checked={settings.auto_create_notes}
          onChange={(value) => setValue("auto_create_notes", value)}
        />
        <SettingToggle
          label="更新已有条目需审核"
          detail="保护人工编辑和既有结论"
          checked={settings.review_updates}
          onChange={(value) => setValue("review_updates", value)}
        />
      </section>

      <section className="knowledge-setting-section knowledge-grid-section">
        <div className="knowledge-section-heading">
          <Search size={18} />
          <div><strong>检索与隐私</strong><span>调整召回范围和私密来源处理</span></div>
        </div>
        <label className="knowledge-select-row">
          <span><strong>默认召回数量</strong><small>每次查询读取的候选上限</small></span>
          <select
            value={settings.max_search_results}
            onChange={(event) => setValue("max_search_results", Number(event.target.value))}
          >
            {[5, 8, 12, 20].map((value) => <option key={value} value={value}>{value} 条</option>)}
          </select>
        </label>
        <SettingToggle
          label="允许私密来源发送给模型"
          detail="关闭时仅使用本地搜索和摘要"
          checked={settings.allow_private_remote}
          onChange={(value) => setValue("allow_private_remote", value)}
        />
      </section>

      <section className="knowledge-setting-section knowledge-grid-section">
        <div className="knowledge-section-heading">
          <FileClock size={18} />
          <div><strong>网页更新监控</strong><span>按当前 Profile 定期检查已收录网页</span></div>
        </div>
        <SettingToggle
          label="启用定时检查"
          detail="后台仅检查已明确关注的网页来源"
          checked={settings.web_update_enabled}
          onChange={(value) => setValue("web_update_enabled", value)}
        />
        <SettingToggle
          label="自动关注新网页"
          detail="以后收录的网页自动加入更新检查"
          checked={settings.auto_watch_web_sources}
          onChange={(value) => setValue("auto_watch_web_sources", value)}
        />
        <label className="knowledge-select-row">
          <span><strong>默认检查间隔</strong><small>单个来源可在知识库工作区单独启用</small></span>
          <select value={settings.web_update_interval_minutes} onChange={(event) => setValue("web_update_interval_minutes", Number(event.target.value))}>
            <option value={60}>每小时</option><option value={360}>每 6 小时</option><option value={1440}>每天</option><option value={10080}>每周</option>
          </select>
        </label>
      </section>

      <section className="knowledge-setting-section">
        <div className="knowledge-section-heading">
          <BookOpenCheck size={18} />
          <div><strong>知识库目的</strong><span>作为编译、筛选和回答的长期边界</span></div>
        </div>
        <textarea
          className="knowledge-purpose"
          value={settings.purpose}
          spellCheck={false}
          onChange={(event) => setValue("purpose", event.target.value)}
          aria-label="知识库目的"
        />
      </section>

      <section className="knowledge-setting-section">
        <div className="knowledge-section-heading">
          <FolderOpen size={18} />
          <div><strong>存储与维护</strong><span className="knowledge-path">{settings.root_path || status?.root_path}</span></div>
        </div>
        <div className="knowledge-storage-picker">
          <input value={storagePath} onChange={(event) => setStoragePath(event.target.value)} spellCheck={false} aria-label="知识库存储路径" />
          <button disabled={busy} onClick={() => void chooseKnowledgeStorage().then((result) => { if (result.path) setStoragePath(result.path); }).catch((error) => setNotice({ tone: "error", text: String(error) }))}>选择</button>
          <button disabled={busy} title="打开知识库文件夹" onClick={() => void openKnowledgeStorage().catch((error) => setNotice({ tone: "error", text: String(error) }))}><FolderOpen size={16} /></button>
        </div>
        <div className="knowledge-maintenance-actions">
          <button disabled={busy || !storagePath.trim() || storagePath.trim() === settings.root_path} onClick={() => { if (window.confirm("切换后将迁移空目录并自动重建知识索引。确认继续？")) void runAction("relocating", () => changeKnowledgeStorage(storagePath.trim()), "知识库位置已切换，索引已重建"); }}>
            {action === "relocating" ? <LoaderCircle className="is-spinning" size={16} /> : <FolderOpen size={16} />}切换位置
          </button>
          <button disabled={busy} onClick={() => void runAction("linting", lintKnowledge, "知识库健康检查已完成")}>
            {action === "linting" ? <LoaderCircle className="is-spinning" size={16} /> : <FileCheck2 size={16} />}
            健康检查
          </button>
          <button disabled={busy} onClick={() => void runSemanticLint()}>
            {action === "semantic-linting" ? <LoaderCircle className="is-spinning" size={16} /> : <Search size={16} />}语义检查
          </button>
          <button
            disabled={busy}
            onClick={() => {
              if (window.confirm("重建前会自动备份数据库。确认继续？")) {
                void runAction("rebuilding", rebuildKnowledgeIndex, "知识索引已从 Markdown 重建");
              }
            }}
          >
            {action === "rebuilding" ? <LoaderCircle className="is-spinning" size={16} /> : <RefreshCw size={16} />}
            重建索引
          </button>
        </div>
      </section>

      <div className="knowledge-save-bar">
        <span>{settings.enabled ? "知识库已启用" : "知识库已停用"}</span>
        <button
          className="knowledge-save-button"
          disabled={busy}
          onClick={() => void runAction("saving", () => updateKnowledgeSettings(settings), "知识库设置已保存")}
        >
          {action === "saving" ? <LoaderCircle className="is-spinning" size={16} /> : <Save size={16} />}
          保存设置
        </button>
      </div>
    </div>
  );
}

function Metric({ label, value, icon: Icon }: { label: string; value: number; icon: typeof Database }) {
  return (
    <div className="knowledge-metric">
      <Icon size={17} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SettingToggle({
  label,
  detail,
  checked,
  onChange
}: {
  label: string;
  detail: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <div className="knowledge-toggle-row">
      <span><strong>{label}</strong><small>{detail}</small></span>
      <button
        type="button"
        className={checked ? "knowledge-toggle is-on" : "knowledge-toggle"}
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
      >
        <span />
      </button>
    </div>
  );
}
