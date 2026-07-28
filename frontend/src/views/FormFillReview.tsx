import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, CircleHelp, Database, FileWarning, ShieldCheck } from "lucide-react";
import { applyFormFillSession, getFormFillSession } from "../api/client";
import type { FormFillField, FormFillSession, FormSessionApplyPayload } from "../types/api";

type FieldInstruction = FormSessionApplyPayload["fields"][string];

const statusLabel: Record<FormFillField["status"], string> = {
  ready: "可直接填写",
  choose: "请选择资料",
  confirm: "需要确认",
  existing: "已有内容",
  missing: "资料缺失",
  ignore: "已忽略",
  defer: "以后处理",
  filled: "已填写",
};

export function FormFillReview({ initialSession, onError }: { initialSession: Partial<FormFillSession> & Pick<FormFillSession, "session_id">; onError: (message: string | null) => void }) {
  const [session, setSession] = useState<FormFillSession | null>(() => Array.isArray(initialSession.fields) ? initialSession as FormFillSession : null);
  const [groups, setGroups] = useState<Record<string, string>>({});
  const [fields, setFields] = useState<Record<string, FieldInstruction>>({});
  const [remember, setRemember] = useState(false);
  const [saving, setSaving] = useState(false);
  const [resultMessage, setResultMessage] = useState("");

  const reviewFields = useMemo(() => session?.fields.filter((field) => field.status !== "filled") ?? [], [session]);
  const filledCount = session?.fields.filter((field) => field.status === "filled").length ?? 0;

  useEffect(() => {
    if (session) {
      setGroups(Object.fromEntries(session.groups.filter((group) => group.selected_record_id)
        .map((group) => [group.group_key, group.selected_record_id as string])));
      return;
    }
    let active = true;
    getFormFillSession(initialSession.session_id).then((loaded) => {
      if (active) setSession(loaded);
    }).catch((reason) => onError(reason instanceof Error ? reason.message : String(reason)));
    return () => { active = false; };
  }, [initialSession.session_id, onError, session]);

  function selectedValue(field: FormFillField) {
    const instruction = fields[field.field_id];
    if (instruction?.value !== undefined) return instruction.value;
    const recordId = groups[field.record_key];
    return field.candidates.find((candidate) => candidate.record_id === recordId)?.value ?? field.selected?.value ?? "";
  }

  function updateField(fieldId: string, patch: FieldInstruction) {
    setFields((current) => ({ ...current, [fieldId]: { ...current[fieldId], ...patch } }));
  }

  async function apply() {
    if (!session) return;
    setSaving(true);
    setResultMessage("");
    onError(null);
    try {
      const payloadFields = { ...fields };
      session.fields.forEach((field) => {
        const existingAction = payloadFields[field.field_id]?.action;
        if (field.status === "choose" && groups[field.record_key] && existingAction !== "skip"
          && (!field.current_value || existingAction === "fill")) {
          payloadFields[field.field_id] = {
            ...payloadFields[field.field_id], action: "fill", value: selectedValue(field),
            replace_existing: Boolean(payloadFields[field.field_id]?.replace_existing),
          };
        }
      });
      const result = await applyFormFillSession(session.session_id, {
        groups, fields: payloadFields, remember, apply_ready: true,
      });
      setSession(result.form_session);
      setResultMessage(`已填写 ${result.filled_count} 项，${result.skipped.length} 项因页面内容变化或控件限制而跳过；表单未提交。`);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  if (!session) return <section className="form-fill-review is-loading" aria-label="正在读取本地填写预览"><p>正在从本地资料库读取填写候选…</p></section>;

  return <section className="form-fill-review" aria-label="网页表单填写确认">
    <header>
      <div><ShieldCheck size={18} /><span><strong>填写检查</strong><small>{session.title || "当前网页"}</small></span></div>
      <div className="form-fill-summary">
        <span className="is-filled">{filledCount} 已填</span>
        <span>{session.summary.choose ?? 0} 待选</span>
        <span>{session.summary.confirm ?? 0} 待确认</span>
        <span>{session.summary.missing ?? 0} 缺失</span>
      </div>
    </header>

    {session.groups.filter((group) => group.status === "choose").map((group) => <label className="form-fill-group" key={group.group_key}>
      <span><Database size={14} /><strong>{group.category === "education" ? "教育经历" : group.category === "work" ? "工作/实习经历" : group.category === "project" ? "项目经历" : "关联资料"}</strong><small>整组字段将来自同一条记录</small></span>
      <select value={groups[group.group_key] ?? ""} onChange={(event) => setGroups((current) => ({ ...current, [group.group_key]: event.target.value }))}>
        <option value="">请选择一条资料</option>
        {group.candidates.map((candidate) => <option key={candidate.record_id} value={candidate.record_id}>{candidate.label}</option>)}
      </select>
    </label>)}

    <div className="form-fill-fields">
      {reviewFields.map((field) => {
        const instruction = fields[field.field_id] ?? {};
        const value = selectedValue(field);
        const requiresOptIn = ["confirm", "existing", "missing"].includes(field.status);
        const isLong = field.control_type === "textarea" || value.length > 120;
        return <article className={`form-fill-field is-${field.status}`} key={field.field_id}>
          <div className="form-fill-field-heading">
            <span>{field.status === "missing" ? <FileWarning size={14} /> : field.status === "confirm" || field.status === "existing" ? <AlertTriangle size={14} /> : field.status === "choose" ? <CircleHelp size={14} /> : <Check size={14} />}</span>
            <div><strong>{field.label}</strong><small>{field.section_title || field.reason}</small></div>
            <em>{statusLabel[field.status]}</em>
          </div>

          {field.current_value && <div className="form-fill-existing"><span>网页现有</span><strong>{field.current_value}</strong></div>}

          {field.status === "missing" ? <>
            <textarea rows={2} value={instruction.value ?? ""} placeholder="临时填写内容" onChange={(event) => updateField(field.field_id, { value: event.target.value })} />
            <div className="form-fill-field-actions">
              <button type="button" onClick={() => updateField(field.field_id, { action: "fill", save_to_profile: false })}>仅本次填写</button>
              <button type="button" onClick={() => updateField(field.field_id, { action: "fill", save_to_profile: true, remember: true })}>填写并存入资料库</button>
              <button type="button" onClick={() => updateField(field.field_id, { action: "ignore", remember })}>忽略</button>
              <button type="button" onClick={() => updateField(field.field_id, { action: "defer", remember: true })}>以后处理</button>
            </div>
          </> : <>
            {isLong ? <textarea rows={3} value={value} onChange={(event) => updateField(field.field_id, { value: event.target.value })} />
              : <input value={value} onChange={(event) => updateField(field.field_id, { value: event.target.value })} />}
            {(requiresOptIn || field.status === "choose") && <label className="form-fill-check">
              <input type="checkbox" checked={field.status === "choose"
                ? Boolean(groups[field.record_key]) && (field.current_value ? instruction.action === "fill" : instruction.action !== "skip")
                : instruction.action === "fill"}
                disabled={field.status === "choose" && !groups[field.record_key]}
                onChange={(event) => updateField(field.field_id, {
                  action: event.target.checked ? "fill" : "skip",
                  replace_existing: field.current_value ? event.target.checked : instruction.replace_existing,
                })} />
              <span>{field.current_value ? "确认替换网页现有内容" : "确认填写此字段"}</span>
            </label>}
          </>}
          <p>{field.reason} · 匹配度 {Math.round(field.confidence * 100)}%</p>
        </article>;
      })}
    </div>

    <footer>
      <label><input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} />记住本次选择和修改</label>
      <button type="button" disabled={saving} onClick={() => void apply()}>{saving ? "正在填写…" : "确认填写（不会提交）"}</button>
    </footer>
    {resultMessage && <p className="form-fill-result" role="status">{resultMessage}</p>}
  </section>;
}
