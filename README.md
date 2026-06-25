# DeskPilot — 桌灵

Windows 个人桌面助手。自然语言下达任务 → Agent 感知桌面上下文 → 自动执行 → 结果反馈。

```
"总结当前网页并保存" → 悬浮窗 → LangGraph → 浏览器扩展 → OpenAI → Markdown
```

## 架构

```
Tauri 悬浮窗 (React + TypeScript)
       │ HTTP + SSE
       ▼
FastAPI 本地服务 (127.0.0.1:8765)
       │
       ▼
LangGraph 编排核心
       ├── 上下文感知（窗口识别 / 浏览器 / 截图 OCR）
       ├── 工具路由（Playwright / UIA / RPA / 文件）
       ├── 安全层（权限 / 审批 / 审计）
       └── 记忆层（短期状态 / FTS5 长期记忆）
```

## 技术栈

| 层 | 技术 |
|---|---|
| 桌面壳 | Tauri |
| 前端 | React + Vite + TypeScript + Tailwind CSS + shadcn/ui |
| 状态管理 | Zustand |
| 后端 | Python 3.12 + FastAPI |
| 包管理 | uv |
| Agent | LangGraph |
| 模型 | OpenAI SDK |
| 数据库 | SQLite + FTS5 |
| 浏览器上下文 | Chrome/Edge Manifest V3 扩展 |
| 浏览器自动化 | Playwright |
| Windows 自动化 | pywin32 + pywinauto |
| RPA 视觉 | mss + opencv-python + PaddleOCR |
| 实时事件 | SSE |

## 快速开始

```bash
# 后端
uv sync
uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8765

# 前端
cd frontend && npm install && npm run dev

# 浏览器扩展
# Chrome/Edge → 扩展管理 → 加载已解压的扩展 → 选择 browser-extension/
```

## 开发路线

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | 项目骨架 — 前后端工程、Agent 内核、Tool Registry | 进行中 |
| 1 | 悬浮窗 + 当前窗口识别 | 待开始 |
| 2 | 网页操作闭环（总结、表格导出） | 待开始 |
| 3 | 桌面应用 + 基础 RPA（网易云音乐） | 待开始 |
| 4 | 微信 RPA 可见内容采集 | 待开始 |
| 5 | 开发者插件化 | 待开始 |

## 第一阶段验收链路

```
打开网页 → 唤起悬浮窗 → 输入"总结当前网页并保存"
  → 浏览器扩展上报上下文 → FastAPI 创建任务
  → LangGraph 识别 web_page_summary → OpenAI 总结
  → 写入 Markdown → SSE 推送完成
```

## 目录

```text
DeskPilot/
  backend/               FastAPI + LangGraph + OpenAI
  frontend/              Tauri + React 悬浮窗
  browser-extension/     Manifest V3 浏览器扩展
  data/                  本地数据（不入 git）
  report/                设计文档
```

## 安全

- 读取聊天记录、发送消息、删除文件等敏感操作必须用户确认
- 打开应用、总结网页、创建本地导出文件等低风险操作可自动执行
- 微信聊天正文不进入通用日志；截图只存任务目录
- Agent 不允许执行任意 shell 命令

## 文档

- [技术方案](report/技术方案.md)
- [开发规范](report/开发规范.md)
- [接口协议](report/接口与事件协议.md)
- [数据库设计](report/数据库与记忆设计.md)
- [项目骨架](report/项目骨架设计.md)
- [第一阶段任务](report/第一阶段任务清单.md)
