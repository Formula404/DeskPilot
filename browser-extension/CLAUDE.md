# browser-extension — Chrome/Edge 浏览器扩展

Manifest V3 扩展，为 DeskPilot 提供当前浏览器页面的上下文读写能力。

## 职责

- 获取当前 tab 的 URL、标题、可见文本、DOM 摘要
- 执行被授权的轻量页面内动作（由本地服务下发结构化指令）
- 将页面上下文通过 HTTP 上报给本地 FastAPI（`POST /context/browser/current-page`）

## 约束

- **禁止** 调用 OpenAI 或任何外部 AI API
- **禁止** 保存长期数据（不写 localStorage、IndexedDB 用于持久化）
- **禁止** 自行规划任务或自主决策
- **禁止** 直接访问本地数据库
- 所有页面动作必须来自本地服务的结构化指令，不能自行发挥

## 文件组织

```
browser-extension/
  src/
    background.ts    # Service Worker
    content.ts       # Content Script（读取页面、执行轻量动作）
    messaging.ts     # 消息通信
  public/
    manifest.json    # Manifest V3 声明
```

## 数据流

```
Content Script 采集页面上下文
  → 发送给 background Service Worker
  → HTTP POST → 127.0.0.1:8765/context/browser/current-page
  → FastAPI 存入 browser_contexts 表

用户任务触发页面操作
  → FastAPI 生成结构化指令
  → 扩展接收指令 → Content Script 执行 → 返回结果
```

## 权限

- `activeTab` — 当前活动标签页
- `scripting` — 注入 content script
- `storage` — 最小化使用，仅运行时状态
- Host permission: `http://127.0.0.1:8765/*` — 与本地服务通信

## 第一阶段

第一版只实现"读取当前网页上下文并上报"，暂不实现页面内动作执行。
