import { useEffect, useState } from "react";
import { CheckCircle2, Eye, EyeOff, LoaderCircle, Save, Unplug } from "lucide-react";
import { getApplicationSettings, testAIConnection, updateApplicationSettings } from "../api/client";
import { applyRuntimePreferences } from "../settings/runtimePreferences";
import type { ApplicationSettings, ApplicationSettingsUpdate } from "../types/api";

type Section = "ai" | "general";
type Feedback = { tone: "success" | "error"; message: string } | null;

export function ApplicationSettingsPanel({ section }: { section: Section }) {
  const [settings, setSettings] = useState<ApplicationSettings | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [keyTouched, setKeyTouched] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const [feedback, setFeedback] = useState<Feedback>(null);

  useEffect(() => {
    let alive = true;
    getApplicationSettings()
      .then((result) => alive && setSettings(result))
      .catch((error) => alive && setFeedback({ tone: "error", message: String(error) }));
    return () => { alive = false; };
  }, []);

  function changeAI<Key extends keyof ApplicationSettings["ai"]>(key: Key, value: ApplicationSettings["ai"][Key]) {
    setSettings((current) => current ? { ...current, ai: { ...current.ai, [key]: value } } : current);
  }

  function changeGeneral<Key extends keyof ApplicationSettings["general"]>(key: Key, value: ApplicationSettings["general"][Key]) {
    setSettings((current) => current ? { ...current, general: { ...current.general, [key]: value } } : current);
  }

  function payload(): ApplicationSettingsUpdate | null {
    if (!settings) return null;
    const { api_key_configured: _configured, api_key_hint: _hint, ...ai } = settings.ai;
    return {
      schema_version: settings.schema_version,
      ai: { ...ai, api_key: keyTouched ? apiKey : null },
      general: settings.general
    };
  }

  async function save() {
    const update = payload();
    if (!update) return;
    setBusy("save");
    setFeedback(null);
    try {
      const result = await updateApplicationSettings(update);
      setSettings(result);
      setApiKey("");
      setKeyTouched(false);
      applyRuntimePreferences(result);
      setFeedback({ tone: "success", message: "设置已保存并立即生效" });
    } catch (error) {
      setFeedback({ tone: "error", message: error instanceof Error ? error.message : String(error) });
    } finally {
      setBusy(null);
    }
  }

  async function testConnection() {
    setBusy("test");
    setFeedback(null);
    try {
      const result = await testAIConnection();
      setFeedback({ tone: "success", message: result.message });
    } catch (error) {
      setFeedback({ tone: "error", message: error instanceof Error ? error.message : String(error) });
    } finally {
      setBusy(null);
    }
  }

  if (!settings) {
    return <div className="application-settings-loading"><LoaderCircle className="spin" size={22} /> 正在读取设置…</div>;
  }

  return (
    <div className="application-settings">
      {section === "ai" ? (
        <>
          <div className="settings-section-heading" data-motion="settings-page-item">
            <div><h2>模型服务</h2><p>支持 OpenAI 及兼容 OpenAI API 的服务。保存后所有 AI 任务会使用这里的参数。</p></div>
            <span className={settings.ai.api_key_configured ? "config-badge is-ready" : "config-badge"}>
              {settings.ai.api_key_configured ? "已配置" : "待配置"}
            </span>
          </div>
          <div className="settings-form-grid">
            <label className="settings-field settings-field-wide" data-motion="settings-page-item">
              <span>API 地址</span>
              <input value={settings.ai.base_url} onChange={(event) => changeAI("base_url", event.target.value)} placeholder="https://api.openai.com/v1" />
              <small>填写包含版本路径的根地址，例如 /v1。</small>
            </label>
            <label className="settings-field" data-motion="settings-page-item">
              <span>模型</span>
              <input value={settings.ai.model} onChange={(event) => changeAI("model", event.target.value)} placeholder="gpt-4.1-mini" />
            </label>
            <label className="settings-field" data-motion="settings-page-item">
              <span>请求超时（秒）</span>
              <input type="number" min={5} max={600} value={settings.ai.request_timeout_seconds} onChange={(event) => changeAI("request_timeout_seconds", Number(event.target.value))} />
            </label>
            <label className="settings-field settings-field-wide" data-motion="settings-page-item">
              <span>API Key {settings.ai.api_key_hint && <em>当前：{settings.ai.api_key_hint}</em>}</span>
              <div className="secret-input">
                <input type={showKey ? "text" : "password"} value={apiKey} onChange={(event) => { setApiKey(event.target.value); setKeyTouched(true); }} placeholder={settings.ai.api_key_configured ? "留空表示保持当前 Key" : "请输入 API Key"} autoComplete="off" />
                <button type="button" onClick={() => setShowKey((value) => !value)} aria-label={showKey ? "隐藏 API Key" : "显示 API Key"}>{showKey ? <EyeOff size={17} /> : <Eye size={17} />}</button>
              </div>
              <small>Key 不会回传到界面；清空输入并保存可移除已保存的 Key。</small>
            </label>
            <label className="settings-field settings-field-wide" data-motion="settings-page-item">
              <span>温度 <strong>{settings.ai.temperature.toFixed(1)}</strong></span>
              <input type="range" min={0} max={2} step={0.1} value={settings.ai.temperature} onChange={(event) => changeAI("temperature", Number(event.target.value))} />
              <small>数值越低结果越稳定，越高则更有发散性。</small>
            </label>
          </div>
        </>
      ) : (
        <>
          <div className="settings-section-heading" data-motion="settings-page-item"><div><h2>体验偏好</h2><p>这些偏好保存在本机，并会应用到所有 DeskPilot 窗口。</p></div></div>
          <div className="settings-form-grid">
            <label className="settings-field settings-field-wide" data-motion="settings-page-item">
              <span>AI 默认回复语言</span>
              <select value={settings.general.response_language} onChange={(event) => changeGeneral("response_language", event.target.value as ApplicationSettings["general"]["response_language"])}>
                <option value="zh-CN">简体中文</option><option value="en">English</option>
              </select>
            </label>
            <label className="settings-field settings-field-wide" data-motion="settings-page-item">
              <span>界面动效</span>
              <select value={settings.general.motion_mode} onChange={(event) => changeGeneral("motion_mode", event.target.value as ApplicationSettings["general"]["motion_mode"])}>
                <option value="system">跟随系统</option><option value="reduced">减少动效</option><option value="full">完整动效</option>
              </select>
              <small>“减少动效”会把入场与切换动画缩短到近乎即时。</small>
            </label>
          </div>
        </>
      )}

      <div className="settings-form-footer" data-motion="settings-page-item">
        <div className={feedback ? `settings-feedback is-${feedback.tone}` : "settings-feedback"}>
          {feedback && <><CheckCircle2 size={16} /> {feedback.message}</>}
        </div>
        {section === "ai" && <button className="secondary-action" disabled={busy !== null || !settings.ai.api_key_configured} onClick={() => void testConnection()}><Unplug size={16} />{busy === "test" ? "连接中…" : "测试连接"}</button>}
        <button className="primary-action" disabled={busy !== null} onClick={() => void save()}><Save size={16} />{busy === "save" ? "保存中…" : "保存设置"}</button>
      </div>
    </div>
  );
}
