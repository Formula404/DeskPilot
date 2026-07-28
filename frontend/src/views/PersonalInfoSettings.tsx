import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Award, BadgeCheck, BriefcaseBusiness, Check, CircleAlert, Ellipsis, FolderKanban, GraduationCap,
  KeyRound, LayoutGrid, Mail, MapPin, MessageSquareText, Pencil, Plus, SlidersHorizontal,
  Trash2, Trophy, UserRound, Wrench, X,
  type LucideIcon,
} from "lucide-react";
import {
  createPersonalInfo, createPersonalInfoRecord, deleteFormFillMemory, deletePersonalInfo,
  deletePersonalInfoRecord, deletePersonalInfoRecordField, getPersonalInfo, updateFormFillMemory,
  updatePersonalInfo, updatePersonalInfoRecordField,
} from "../api/client";
import type { FormFillMemory, PersonalInfoField, PersonalInfoOverview, PersonalInfoRecord, PersonalInfoRecordField } from "../types/api";

const empty: PersonalInfoOverview = { categories: {}, items: [], records: [], form_memories: [] };

const categoryMeta: Record<string, { icon: LucideIcon; description: string }> = {
  identity: { icon: UserRound, description: "姓名、性别、出生日期等身份字段" },
  contact: { icon: Mail, description: "邮箱、电话和个人网站等联系方式" },
  address: { icon: MapPin, description: "国家、城市、街道和邮政编码" },
  work: { icon: BriefcaseBusiness, description: "公司、职位等工作相关信息" },
  education: { icon: GraduationCap, description: "学校、学历、学位和专业" },
  project: { icon: FolderKanban, description: "项目名称、角色、主要工作、技能和成果" },
  skill: { icon: Wrench, description: "可保存多项技能及熟练程度" },
  certificate: { icon: Award, description: "证书、发证机构、时间与编号" },
  award: { icon: Trophy, description: "奖项、授奖机构、时间和说明" },
  qa: { icon: MessageSquareText, description: "自我评价、个人优势、离职原因等多版本答案" },
  preference: { icon: SlidersHorizontal, description: "语言及其他个人偏好" },
  other: { icon: Ellipsis, description: "尚未归入固定分类的自定义字段" },
};

type CategoryFilter = "all" | "pending" | string;

export function PersonalInfoSettingsPanel() {
  const [data, setData] = useState(empty);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<PersonalInfoField | null>(null);
  const [adding, setAdding] = useState(false);
  const [addingRecord, setAddingRecord] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<CategoryFilter>("all");
  const [editingRecordField, setEditingRecordField] = useState<{ record: PersonalInfoRecord; field: PersonalInfoRecordField } | null>(null);
  const [editingMemory, setEditingMemory] = useState<FormFillMemory | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    getPersonalInfo()
      .then((result) => {
        setData({ ...result, records: result.records ?? [], form_memories: result.form_memories ?? [] });
        setError("");
      })
      .catch((reason) => setError(String(reason)))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    load();
    const refresh = () => load();
    window.addEventListener("deskpilot:personal-info-refresh", refresh);
    return () => window.removeEventListener("deskpilot:personal-info-refresh", refresh);
  }, [load]);
  const navigation = useMemo(() => [
    { key: "all", label: "全部信息", icon: LayoutGrid, count: data.items.length + (data.records?.length ?? 0) },
    { key: "pending", label: "待确认", icon: CircleAlert, count: data.items.filter((item) => item.status === "proposed").length + (data.records ?? []).filter((item) => item.status === "proposed").length },
    { key: "memories", label: "填写记忆", icon: KeyRound, count: data.form_memories?.length ?? 0 },
    ...Object.entries(data.categories).map(([key, label]) => ({
      key, label, icon: categoryMeta[key]?.icon ?? Ellipsis,
      count: data.items.filter((item) => item.category === key).length + (data.records ?? []).filter((item) => item.category === key).length,
    })),
  ], [data]);
  const visibleItems = useMemo(() => data.items.filter((item) => activeCategory !== "memories" &&
    activeCategory === "all" || (activeCategory === "pending" ? item.status === "proposed" : item.category === activeCategory)
  ), [activeCategory, data.items]);
  const visibleRecords = useMemo(() => (data.records ?? []).filter((item) => activeCategory !== "memories" &&
    activeCategory === "all" || (activeCategory === "pending" ? item.status === "proposed" : item.category === activeCategory)
  ), [activeCategory, data.records]);
  const activeLabel = activeCategory === "all" ? "全部信息" : activeCategory === "pending" ? "待确认" : activeCategory === "memories" ? "填写记忆" : data.categories[activeCategory] ?? "个人信息";
  const activeDescription = activeCategory === "all"
    ? "集中查看所有可用于智能表单的资料"
    : activeCategory === "pending"
      ? "这些信息来自聊天推断，确认后才会用于填写"
      : activeCategory === "memories"
        ? "查看、修改或删除字段关联、站点偏好和暂缓处理规则"
      : categoryMeta[activeCategory]?.description ?? "管理这一分类下的个人信息";

  async function remove(item: PersonalInfoField) {
    if (!window.confirm(`删除“${item.label}”？`)) return;
    try { await deletePersonalInfo(item.id); load(); } catch (reason) { setError(String(reason)); }
  }

  async function confirm(item: PersonalInfoField) {
    try { await updatePersonalInfo(item.id, { status: "confirmed" }); load(); } catch (reason) { setError(String(reason)); }
  }

  async function removeRecord(record: PersonalInfoRecord) {
    if (!window.confirm(`删除关联记录“${record.label}”？`)) return;
    try { await deletePersonalInfoRecord(record.id); load(); } catch (reason) { setError(String(reason)); }
  }

  async function removeMemory(memory: FormFillMemory) {
    if (!window.confirm(`删除“${memory.field_label || memory.field_key || "未命名字段"}”的填写记忆？`)) return;
    try { await deleteFormFillMemory(memory.id); load(); } catch (reason) { setError(String(reason)); }
  }

  const isRecordCategory = (data.record_categories ?? []).includes(activeCategory);

  return <div className="personal-info-panel">
    <aside className="personal-info-categories" aria-label="个人信息分类">
      <div className="personal-info-category-summary"><BadgeCheck size={17} /><span><strong>{data.items.filter((item) => item.status === "confirmed").length + (data.records ?? []).filter((item) => item.status === "confirmed").length}</strong><small>项已确认资料</small></span></div>
      <div className="personal-info-category-list" role="tablist" aria-orientation="vertical">
        {navigation.map((entry) => {
          const Icon = entry.icon;
          return <button key={entry.key} role="tab" aria-selected={activeCategory === entry.key}
            className={`${activeCategory === entry.key ? "is-active" : ""} ${entry.key === "pending" && entry.count ? "has-pending" : ""}`}
            onClick={() => setActiveCategory(entry.key)}>
            <Icon size={16} /><span>{entry.label}</span><small>{entry.count}</small>
          </button>;
        })}
      </div>
      <p>密码、验证码、文件和支付信息始终不会被记录。</p>
    </aside>
    <section className="personal-info-browser" role="tabpanel">
      <header className="personal-info-heading">
        <div><span className="personal-info-eyebrow">个人信息分类</span><h2>{activeLabel}</h2><p>{activeDescription}</p></div>
        {activeCategory !== "memories" && activeCategory !== "pending" && <button className="personal-info-add" onClick={() => isRecordCategory ? setAddingRecord(activeCategory) : setAdding(true)}><Plus size={15} /> {isRecordCategory ? "新增记录" : "新增信息"}</button>}
      </header>
      {error && <div className="personal-info-error">{error}<button onClick={() => setError("")}><X size={13} /></button></div>}
      <div className="personal-info-list">
        {loading ? <div className="personal-info-loading"><span /><span /><span /></div>
          : activeCategory === "memories" ? (data.form_memories?.length ? data.form_memories.map((memory) => <div className="personal-info-row" key={memory.id}>
            <div className="personal-info-row-copy"><div><strong>{memory.field_label || memory.field_key || "未命名字段"}</strong><span className="personal-info-category-chip">{memory.action === "map" ? "字段关联" : memory.action === "literal" ? "站点专用值" : memory.action === "ignore" ? "忽略" : "以后处理"}</span></div>
              <span>{memory.override_value || memory.source_record_label || memory.source_field_label || "不填写"}</span>
              <small>{memory.origin}{memory.path_pattern} · 已应用 {memory.use_count} 次</small></div>
            <div className="personal-info-actions"><button title="编辑记忆" onClick={() => setEditingMemory(memory)}><Pencil size={14} /></button><button className="is-delete" title="删除记忆" onClick={() => void removeMemory(memory)}><Trash2 size={14} /></button></div>
          </div>) : <div className="personal-info-empty-state"><div><KeyRound size={22} /></div><strong>暂无填写记忆</strong><span>确认字段选择或勾选“记住本次选择”后会出现在这里</span></div>)
          : visibleItems.length === 0 && visibleRecords.length === 0 ? <div className="personal-info-empty-state">
            <div>{activeCategory === "pending" ? <Check size={22} /> : <Plus size={22} />}</div>
            <strong>{activeCategory === "pending" ? "没有待确认的信息" : `暂无${activeLabel}`}</strong>
            <span>{activeCategory === "pending" ? "聊天识别的新资料会出现在这里" : "可以手动新增，或让 DeskPilot 记住网页表单"}</span>
            {activeCategory !== "pending" && <button onClick={() => isRecordCategory ? setAddingRecord(activeCategory) : setAdding(true)}>新增第一项</button>}
          </div> : <>
          {visibleRecords.map((record) => <article className="personal-info-record" key={record.id}>
            <header><div><span>{data.categories[record.category] ?? "关联资料"}</span><strong>{record.label}</strong></div>
              <button className="is-delete" title="删除关联记录" onClick={() => void removeRecord(record)}><Trash2 size={14} /></button></header>
            <div className="personal-info-record-grid">{record.fields.map((field) => <button key={field.id} onClick={() => setEditingRecordField({ record, field })}>
              <small>{field.label}</small><strong>{field.value}</strong><Pencil size={12} />
            </button>)}</div>
            <footer><span>作为一条完整{record.category === "education" ? "教育经历" : record.category === "work" ? "工作经历" : "关联记录"}保存，后续将按同一记录回填</span></footer>
          </article>)}
          {visibleItems.map((item) =>
            <div className={`personal-info-row ${item.status === "proposed" ? "is-proposed" : ""}`} key={item.id}>
              <div className="personal-info-row-copy">
                <div><strong>{item.label}</strong><span className="personal-info-category-chip">{data.categories[item.category] ?? "其他信息"}</span></div>
                <span>{item.value}</span>
                <small>{item.status === "proposed" ? `来自聊天 · 匹配置信度 ${Math.round(item.confidence * 100)}%` : sourceLabel(item.source_type)}</small>
              </div>
              <div className="personal-info-actions">
                {item.status === "proposed" && <button className="is-confirm" title="确认使用" onClick={() => void confirm(item)}><Check size={14} /><span>确认使用</span></button>}
                <button title="编辑" onClick={() => setEditing(item)}><Pencil size={14} /></button>
                <button className="is-delete" title="删除" onClick={() => void remove(item)}><Trash2 size={14} /></button>
              </div>
            </div>)}</>}
      </div>
    </section>
    {(editing || adding) && <PersonalInfoEditor item={editing} categories={data.categories}
      defaultCategory={activeCategory !== "all" && activeCategory !== "pending" ? activeCategory : "other"}
      onClose={() => { setEditing(null); setAdding(false); }} onSaved={() => { setEditing(null); setAdding(false); load(); }} />}
    {editingRecordField && <RecordFieldEditor target={editingRecordField} onClose={() => setEditingRecordField(null)}
      onSaved={() => { setEditingRecordField(null); load(); }} />}
    {addingRecord && <PersonalInfoRecordEditor category={addingRecord} categoryLabel={data.categories[addingRecord] ?? "关联资料"}
      onClose={() => setAddingRecord(null)} onSaved={() => { setAddingRecord(null); load(); }} />}
    {editingMemory && <FormMemoryEditor memory={editingMemory} onClose={() => setEditingMemory(null)}
      onSaved={() => { setEditingMemory(null); load(); }} />}
  </div>;
}

function sourceLabel(source: string) {
  return ({ form_capture: "来自已记住表单", user_edit: "手动编辑", user_explicit: "来自明确指令", chat_inferred: "来自聊天" } as Record<string, string>)[source] ?? "已确认";
}

function PersonalInfoEditor({ item, categories, defaultCategory, onClose, onSaved }: { item: PersonalInfoField | null; categories: Record<string, string>; defaultCategory: string; onClose: () => void; onSaved: () => void }) {
  const [category, setCategory] = useState(item?.category ?? defaultCategory);
  const [key, setKey] = useState(item?.field_key ?? "");
  const [label, setLabel] = useState(item?.label ?? "");
  const [value, setValue] = useState(item?.value ?? "");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault(); setSaving(true);
    try {
      if (item) await updatePersonalInfo(item.id, { category, field_key: key, label, value, status: "confirmed" });
      else await createPersonalInfo({ category, field_key: key, label, value });
      onSaved();
    } catch (reason) { setSaveError(String(reason)); } finally { setSaving(false); }
  }
  return <div className="personal-info-modal"><form onSubmit={(event) => void submit(event)}>
    <header><h3>{item ? "编辑个人信息" : "新增个人信息"}</h3><button type="button" onClick={onClose}><X size={16} /></button></header>
    <label>分类<select value={category} onChange={(e) => setCategory(e.target.value)}>{Object.entries(categories).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
    <label>显示名称<input required value={label} onChange={(e) => setLabel(e.target.value)} placeholder="例如：常用邮箱" /></label>
    <label>字段键<input required pattern="[a-z0-9_]+" value={key} onChange={(e) => setKey(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"))} placeholder="例如：email" /></label>
    <label>值<input required value={value} onChange={(e) => setValue(e.target.value)} /></label>
    {saveError && <p className="personal-info-editor-error">{saveError}</p>}
    <footer><button type="button" onClick={onClose}>取消</button><button className="is-primary" disabled={saving}>{saving ? "保存中…" : "保存"}</button></footer>
  </form></div>;
}

function RecordFieldEditor({ target, onClose, onSaved }: { target: { record: PersonalInfoRecord; field: PersonalInfoRecordField }; onClose: () => void; onSaved: () => void }) {
  const [label, setLabel] = useState(target.field.label);
  const [value, setValue] = useState(target.field.value);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault(); setSaving(true);
    try { await updatePersonalInfoRecordField(target.record.id, target.field.field_key, { value, label }); onSaved(); }
    catch (reason) { setError(String(reason)); } finally { setSaving(false); }
  }
  return <div className="personal-info-modal"><form onSubmit={(event) => void submit(event)}>
    <header><div><h3>编辑关联字段</h3><small>{target.record.label} · {target.field.label}</small></div><button type="button" onClick={onClose}><X size={16} /></button></header>
    <label>显示名称<input required value={label} onChange={(event) => setLabel(event.target.value)} /></label>
    <label>{label}<textarea required rows={4} value={value} onChange={(event) => setValue(event.target.value)} /></label>
    {error && <p className="personal-info-editor-error">{error}</p>}
    <footer><button type="button" onClick={() => void deletePersonalInfoRecordField(target.record.id, target.field.field_key).then(onSaved).catch((reason) => setError(String(reason)))}>删除字段</button><button type="button" onClick={onClose}>取消</button><button className="is-primary" disabled={saving}>{saving ? "保存中…" : "保存"}</button></footer>
  </form></div>;
}

const recordDefaults: Record<string, Array<{ field_key: string; label: string }>> = {
  education: [{ field_key: "school", label: "学校" }, { field_key: "major", label: "专业" }],
  work: [{ field_key: "company", label: "公司" }, { field_key: "job_title", label: "岗位" }],
  project: [{ field_key: "project_name", label: "项目名称" }, { field_key: "project_role", label: "项目角色" }],
  skill: [{ field_key: "skill_name", label: "技能名称" }, { field_key: "skill_level", label: "熟练程度" }],
  certificate: [{ field_key: "certificate_name", label: "证书名称" }, { field_key: "certificate_issuer", label: "发证机构" }],
  award: [{ field_key: "award_name", label: "奖项名称" }, { field_key: "award_description", label: "获奖说明" }],
  qa: [{ field_key: "self_evaluation", label: "自我评价" }],
};

function PersonalInfoRecordEditor({ category, categoryLabel, onClose, onSaved }: { category: string; categoryLabel: string; onClose: () => void; onSaved: () => void }) {
  const [fields, setFields] = useState(() => (recordDefaults[category] ?? [{ field_key: "custom_field", label: "字段" }]).map((field) => ({ ...field, value: "" })));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault(); setSaving(true);
    try { await createPersonalInfoRecord({ category, fields: fields.filter((field) => field.value.trim()) }); onSaved(); }
    catch (reason) { setError(String(reason)); } finally { setSaving(false); }
  }
  return <div className="personal-info-modal"><form className="is-record-editor" onSubmit={(event) => void submit(event)}>
    <header><h3>新增{categoryLabel}</h3><button type="button" onClick={onClose}><X size={16} /></button></header>
    {fields.map((field, index) => <div className="personal-info-record-editor-row" key={`${field.field_key}-${index}`}>
      <input required value={field.label} aria-label="显示名称" onChange={(event) => setFields((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, label: event.target.value } : item))} />
      <input required pattern="[a-z0-9_]+" value={field.field_key} aria-label="字段键" onChange={(event) => setFields((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, field_key: event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") } : item))} />
      <textarea rows={2} value={field.value} aria-label="字段值" onChange={(event) => setFields((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, value: event.target.value } : item))} />
      <button type="button" aria-label="移除字段" onClick={() => setFields((current) => current.filter((_, itemIndex) => itemIndex !== index))}><Trash2 size={13} /></button>
    </div>)}
    <button className="personal-info-add-field" type="button" onClick={() => setFields((current) => [...current, { field_key: `custom_field_${current.length + 1}`, label: "自定义字段", value: "" }])}><Plus size={13} />添加字段</button>
    {error && <p className="personal-info-editor-error">{error}</p>}
    <footer><button type="button" onClick={onClose}>取消</button><button className="is-primary" disabled={saving || !fields.some((field) => field.value.trim())}>{saving ? "保存中…" : "保存整条记录"}</button></footer>
  </form></div>;
}

function FormMemoryEditor({ memory, onClose, onSaved }: { memory: FormFillMemory; onClose: () => void; onSaved: () => void }) {
  const [action, setAction] = useState(memory.action);
  const [fieldKey, setFieldKey] = useState(memory.field_key ?? "");
  const [overrideValue, setOverrideValue] = useState(memory.override_value ?? "");
  const [priority, setPriority] = useState(memory.priority);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    try { await updateFormFillMemory(memory.id, { action, field_key: fieldKey || null, override_value: action === "literal" ? overrideValue : null, priority }); onSaved(); }
    catch (reason) { setError(String(reason)); }
  }
  return <div className="personal-info-modal"><form onSubmit={(event) => void submit(event)}>
    <header><div><h3>编辑填写记忆</h3><small>{memory.origin}{memory.path_pattern} · {memory.field_label}</small></div><button type="button" onClick={onClose}><X size={16} /></button></header>
    <label>动作<select value={action} onChange={(event) => setAction(event.target.value as FormFillMemory["action"])}><option value="map">关联个人资料</option><option value="literal">使用站点专用值</option><option value="ignore">忽略字段</option><option value="defer">以后处理</option></select></label>
    <label>标准字段键<input value={fieldKey} onChange={(event) => setFieldKey(event.target.value)} /></label>
    {action === "literal" && <label>站点专用值<textarea required rows={4} value={overrideValue} onChange={(event) => setOverrideValue(event.target.value)} /></label>}
    <label>优先级<input type="number" min={0} max={1000} value={priority} onChange={(event) => setPriority(Number(event.target.value))} /></label>
    {error && <p className="personal-info-editor-error">{error}</p>}
    <footer><button type="button" onClick={onClose}>取消</button><button className="is-primary">保存记忆</button></footer>
  </form></div>;
}
