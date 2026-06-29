# browser-extension — Chrome/Edge 浏览器扩展

Manifest V3 扩展，为 DeskPilot 提供浏览器侧 bridge：当前页面上下文采集、后端指令接收、受控页面动作执行和结果回传。

## 职责

- 建立与本地 FastAPI 的浏览器通信通道，优先使用 WebSocket，HTTP 作为兼容/兜底。
- 根据后端请求采集当前 tab 的 URL、标题、可见文本、DOM 摘要。
- 执行被授权的轻量页面内动作（由本地服务下发结构化指令）。
- 将采集结果和动作结果回传给本地服务；需要落库时由后端写入 `browser_contexts`。

## 约束

- **禁止** 调用 OpenAI 或任何外部 AI API
- **禁止** 保存长期数据（不写 localStorage、IndexedDB 用于持久化）
- **禁止** 自行规划任务或自主决策
- **禁止** 直接访问本地数据库
- 所有页面动作必须来自本地服务的结构化指令，不能自行发挥。
- 扩展不能要求用户点击扩展按钮作为任务主流程；用户主入口是 DeskPilot 悬浮窗/应用发送按钮。

## 文件组织

```
browser-extension/
  src/
    background.ts    # Service Worker（连接本地服务、转发指令、管理 tab）
    content.ts       # Content Script（读取页面、执行轻量动作）
    messaging.ts     # WebSocket/Chrome runtime 消息协议
  public/
    manifest.json    # Manifest V3 声明
```

## 数据流

```
扩展启动 / Service Worker 唤醒
  → 连接本地 FastAPI 浏览器通道（WebSocket）
  → 注册浏览器能力和当前活动 tab 元信息

用户在 DeskPilot 发送任务
  → FastAPI / Agent 判断需要网页上下文或网页动作
  → 后端通过浏览器通道下发 collect_page / click / type / extract 等结构化指令
  → background 转发给目标 tab 的 content script
  → content script 执行采集或动作
  → 扩展通过同一通道回传 result / error
  → 后端写入 browser_contexts、task_steps 或继续 Agent workflow

HTTP `POST /context/browser/current-page` 只作为开发期兼容接口或离线兜底，不作为产品主交互链路。
```

## 权限

- `activeTab` — 当前活动标签页
- `scripting` — 注入 content script
- `storage` — 最小化使用，仅运行时状态
- Host permission: `http://127.0.0.1:8765/*` — 与本地服务通信（HTTP + WebSocket）

## 第一阶段

第一版先建立浏览器通信通道，并实现 `collect_page`。即使暂不开放复杂动作，也要按后端主动下发指令、扩展执行、结果回传的协议组织代码，后续再增量加入 `click`、`type`、`scroll`、`extract_table` 等动作。
