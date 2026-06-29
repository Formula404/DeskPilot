# DeskPilot — 桌灵

Windows 个人桌面助手。自然语言下达任务 → Agent 感知桌面上下文 → 自动执行 → 结果反馈。

```text
"总结当前网页并保存" → 悬浮窗发送 → LangGraph → OpenAI Tool Calling → 浏览器/文件工具 → Markdown
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
       ├── Tool Calling Agent（LLM 决策 / 工具调用 / observation）
       ├── 上下文感知（窗口识别 / 浏览器 / 截图 OCR）
       ├── 工具注册表（浏览器 / Playwright / UIA / RPA / 文件）
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
| Agent | LangGraph + OpenAI Tool Calling |
| 模型 | OpenAI SDK |
| 数据库 | SQLite + FTS5 |
| 浏览器通道 | Chrome/Edge Manifest V3 扩展 + 本地 WebSocket/HTTP |
| 浏览器自动化 | 扩展执行当前页轻量动作 + Playwright 受控浏览器 |
| Windows 自动化 | pywin32 + pywinauto |
| RPA 视觉 | mss + opencv-python + PaddleOCR |
| 实时事件 | SSE |

## 快速开始

```bash
# 后端
uv sync
uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8765

# 前端
cd frontend && npm install

# 网页预览（只启动 Vite，可用浏览器打开 http://localhost:1420）
npm run dev

# Tauri 桌面窗口预览（开发时会拉起原生桌面壳）
npm run tauri -- dev

# 浏览器扩展
cd browser-extension && npm install && npm run build
# Chrome/Edge → 扩展管理 → 加载已解压的扩展 → 选择 browser-extension/dist
```

### Tauri 开发环境依赖

`npm run dev` 只需要 Node/npm，适合先看前端网页界面。

`npm run tauri -- dev` 会编译并启动 Tauri 桌面壳，因此开发机还需要安装 Rust 工具链。若出现 `program not found`、`failed to run 'cargo metadata'`，说明系统找不到 `cargo`。

Windows 安装：

```powershell
winget install Rustlang.Rustup
```

安装后重新打开终端，确认：

```powershell
cargo --version
rustc --version
```

如果后续出现 MSVC/linker/C++ build tools 相关错误，再安装 Visual Studio Build Tools，并勾选 **Desktop development with C++**。至少需要包含：

- MSVC v143 - VS 2022 C++ x64/x86 build tools
- Windows 10/11 SDK
- C++ CMake tools for Windows

Build Tools 装好后，普通 PowerShell 里执行 `where.exe link` 仍可能找不到 `link.exe`，这是正常的。MSVC 链接器通常不会永久加入全局 `Path`，需要在 VS 开发者环境里启动 Tauri：

```text
开始菜单 → x64 Native Tools Command Prompt for VS 2022
```

然后运行：

```cmd
cd /d D:\Work\DeskPilot\frontend
npm run tauri -- dev
```

也可以从普通 PowerShell 先打开已加载 MSVC 环境的新命令行：

```powershell
cmd /k "`"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat`" -arch=x64 && cd /d D:\Work\DeskPilot\frontend"
```

在新窗口中确认：

```cmd
where link
npm run tauri -- dev
```

这些是开发和本地打包 Tauri 时需要的依赖；普通网页预览不需要，最终用户安装打包后的应用也不需要。

## 开发路线

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | 项目骨架 — 前后端工程、Tool Calling Agent、Tool Registry | 进行中 |
| 1 | 悬浮窗 + 当前窗口识别 | 待开始 |
| 2 | 网页操作闭环（总结、表格导出） | 待开始 |
| 3 | 桌面应用 + 基础 RPA（网易云音乐） | 待开始 |
| 4 | 微信 RPA 可见内容采集 | 待开始 |
| 5 | 开发者插件化 | 待开始 |

## 第一阶段验收链路

```
打开网页 → 唤起悬浮窗 → 输入"总结当前网页并保存"
  → FastAPI 创建任务 → LangGraph 进入受限 tool calling loop
  → LLM 调用 browser.collect_current_page 获取当前页上下文
  → LLM 生成总结并调用 file.write_markdown
  → SSE 推送完成
```

## 目录

```text
DeskPilot/
  backend/               FastAPI + LangGraph + OpenAI
  frontend/              Tauri + React 悬浮窗
  browser-extension/     Manifest V3 浏览器扩展（浏览器上下文与动作执行通道）
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
