# DeskPilot

个人桌面助手：Tauri 悬浮窗 → 自然语言任务 → LangGraph Agent → 工具执行 → 结果反馈。

## 技术栈

| 层 | 技术 |
|---|---|
| 桌面 UI | Tauri + React + Vite + TypeScript |
| 前端状态 | Zustand |
| 前端样式 | Tailwind CSS + shadcn/ui |
| 本地服务 | Python 3.12 + FastAPI |
| 包管理 | uv |
| Agent 编排 | LangGraph |
| 模型接入 | OpenAI SDK |
| 数据库 | SQLite |
| 长期记忆检索 | SQLite FTS5 |
| 浏览器通道 | Chrome/Edge Manifest V3 + 本地 WebSocket/HTTP |
| 浏览器自动化 | 扩展执行当前页轻量动作 + Playwright |
| Windows 自动化 | pywin32 + pywinauto |
| RPA 视觉 | mss + opencv-python + PaddleOCR |
| 鼠标键盘 | pyautogui |
| 表格 | openpyxl |
| 实时事件 | SSE |
| 测试 | pytest |

## 架构

```
Tauri 悬浮窗 / 设置页
       │ HTTP + SSE
       ▼
FastAPI 本地服务 (127.0.0.1:8765)
       │
       ▼
LangGraph 编排核心
       │
       ├── 上下文感知层（窗口识别 / 截图 OCR / 浏览器上下文）
       ├── 工具注册与路由（CLI / API / Playwright / RPA）
       ├── 执行安全层（权限 / 审批 / 审计日志）
       └── 记忆层（短期 state / 任务历史 / FTS5 长期记忆）
```

## 目录结构

```
DeskPilot/
  backend/                  # Python FastAPI 本地服务
    app/
      api/                  # HTTP/SSE/WebSocket 路由
      agent/                # LangGraph 图、节点、状态、意图路由
      context/              # 窗口/浏览器/截图上下文采集
      core/                 # 配置、日志、路径
      db/                   # SQLite 连接、迁移、模型
      memory/               # 长期记忆读写、FTS5 检索
      safety/               # 权限判断、审批、风险等级
      tools/                # 可被 Agent 调用的结构化工具
      rpa/                  # 截图、OCR、模板匹配、点击、输入
      schemas/              # Pydantic models
    tests/
  frontend/                 # Tauri + React 悬浮窗
    src/
      api/                  # 后端请求封装
      components/           # 通用 UI 组件
      features/             # 按功能拆分的业务组件
      store/                # Zustand stores
      styles/               # 样式
      types/                # TypeScript 类型
  browser-extension/        # Manifest V3 浏览器扩展，浏览器上下文与动作执行通道
    src/
    public/
  data/                     # 本地数据目录（不上传 git）
    config/
    exports/
    logs/
    screenshots/
    tasks/
  report/                   # 设计文档
```

## 模块依赖方向（禁止反向）

```
api → agent → tools → context / rpa / db
api → safety
agent → safety
agent → memory
tools → safety
tools → db
```

- `tools` 不能依赖 `api`
- `context` 不能依赖 `agent`
- `rpa` 不能依赖 `agent`
- `frontend` 不能访问数据库，不能直接调用 OpenAI
- `browser-extension` 不能访问数据库，不能调用 OpenAI，不能自行规划任务

## 第一阶段目标（当前）

打通网页总结闭环，并为后续网页自动操作预留同一条浏览器通信通道：

```
打开网页 → 唤起悬浮窗 → 输入"总结当前网页并保存"
  → FastAPI 创建任务 → 后端通过浏览器扩展通道请求当前页上下文
  → LangGraph 识别 web_page_summary → OpenAI 总结
  → 写入 Markdown → SSE 推送完成
```

第一阶段不做：微信 RPA、网易云音乐、OCR、pyautogui、向量检索、插件市场。

## 开发命令

```bash
# 后端
cd backend
uv sync
uv run pytest
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8765

# 前端
cd frontend
npm install
npm run dev
npm run build

# 浏览器扩展
cd browser-extension
npm install
npm run build
# 在 Chrome/Edge 中加载 browser-extension/dist 目录
```

## 提交前检查

```bash
uv run pytest    # 后端测试
npm run build    # 前端构建
```

## 子模块 CLAUDE.md

- [backend/CLAUDE.md](backend/CLAUDE.md) — 后端模块职责与依赖规则
- [backend/app/agent/CLAUDE.md](backend/app/agent/CLAUDE.md) — Agent 编排规范
- [backend/app/tools/CLAUDE.md](backend/app/tools/CLAUDE.md) — 工具开发与注册规范
- [backend/app/rpa/CLAUDE.md](backend/app/rpa/CLAUDE.md) — RPA 执行规范
- [backend/app/safety/CLAUDE.md](backend/app/safety/CLAUDE.md) — 安全与审批规范
- [frontend/CLAUDE.md](frontend/CLAUDE.md) — 前端开发规范
- [browser-extension/CLAUDE.md](browser-extension/CLAUDE.md) — 浏览器扩展规范
