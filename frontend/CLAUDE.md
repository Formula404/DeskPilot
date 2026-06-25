# frontend — Tauri 悬浮窗

Tauri + React + Vite + TypeScript，桌面悬浮窗和设置页。

## 技术栈

| 用途 | 技术 |
|---|---|
| 框架 | React + Vite |
| 语言 | TypeScript strict mode |
| 状态管理 | Zustand |
| 样式 | Tailwind CSS + shadcn/ui |
| 桌面壳 | Tauri |
| 通信 | HTTP + SSE 连接本地 FastAPI |

## 目录规范

```
frontend/src/
  api/          # 后端 HTTP 请求封装（统一走这里，组件不直接拼 URL）
  components/   # 通用 UI 组件
  features/     # 按功能拆的业务组件
    assistant/      # 悬浮窗对话
    settings/       # 设置页
    task-events/    # 任务事件流显示
  store/        # Zustand stores
  styles/       # 样式
  types/        # TypeScript 类型定义
```

## 约束

- **禁止** 直接调用 OpenAI SDK 或任何 AI API
- **禁止** 直接访问 SQLite 或任何数据库
- **禁止** 直接执行本机自动化（pyautogui、RPA 等）
- **禁止** 在组件里直接拼接 URL，统一走 `api/` 模块
- API 类型集中放在 `types/`
- Zustand store 只保存 UI 状态、任务状态和设置，不保存大段敏感内容
- 所有后端请求统一走 `api/` 封装

## 悬浮窗行为

- 显示在桌面最前层
- 支持全局快捷键唤起和隐藏
- 唤起时采集当前前台窗口信息作为任务上下文
- 展示 Agent 当前计划、执行步骤、需确认的高风险动作
- 允许一键停止当前任务

## 通信

- 提交任务：`POST /chat`
- 任务状态：`GET /tasks/{id}`
- 实时事件：`GET /events` (SSE)
- 审批：`POST /approvals/{id}`

## 构建

```bash
npm run dev     # 开发
npm run build   # 生产构建
```
