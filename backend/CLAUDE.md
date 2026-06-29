# backend — FastAPI 本地服务

Python 3.12 + FastAPI + LangGraph + SQLite，监听 `127.0.0.1:8765`。

## 子模块职责

| 目录 | 职责 | 边界 |
|---|---|---|
| `app/api/` | HTTP/SSE/WebSocket 路由（/chat, /tasks, /events, /context, /browser, /tools, /approvals） | 只做参数校验、连接管理和响应，不写业务逻辑 |
| `app/agent/` | LangGraph 图、节点、状态定义、意图路由 | 不直接操作 UI 或文件系统 |
| `app/context/` | 当前窗口、浏览器上下文、截图采集 | 不依赖 agent 模块 |
| `app/core/` | 配置加载、日志初始化、路径常量 | 不依赖其他 app 模块 |
| `app/db/` | SQLite 连接管理、表创建、迁移 | 不依赖业务模块 |
| `app/memory/` | 长期记忆读写、FTS5 检索 | 只依赖 db |
| `app/safety/` | 权限判断、审批管理、风险等级、审计日志 | 不依赖 agent |
| `app/tools/` | 工具注册表、基类、各领域工具实现 | 不依赖 api；每个工具必须声明风险等级和权限 |
| `app/rpa/` | 截图、OCR、模板匹配、鼠标键盘、窗口操作 | 不依赖 agent；不使用绝对坐标 |
| `app/schemas/` | Pydantic 模型定义 | 零依赖 |

## 依赖方向

```
api → agent → tools → context / rpa / db
api → safety
agent → safety
agent → memory
tools → safety
tools → db
```

新增代码时检查：是否引入了反向依赖？是否跨层直接访问了不该访问的模块？

## API 约定

- 协议：HTTP + SSE + WebSocket。Tauri 使用 HTTP/SSE；浏览器扩展使用 WebSocket 作为后端主动下发采集/动作指令的主通道，HTTP 作为兼容/兜底。
- 数据格式：JSON
- 时间格式：ISO 8601
- ID 格式：UUID
- 错误返回统一 `{"ok": false, "error": {"code": "...", "message": "...", "detail": {}}}`

## 入口

```python
# backend/app/main.py
from fastapi import FastAPI
```

启动：`uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8765`

## 配置

- `.env` 存放本地密钥和地址
- 用户配置存入 SQLite `settings` 表
- 文件路径统一使用 `pathlib.Path`

## 测试

- API 测试：pytest + FastAPI TestClient
- 工具 handler：单元测试
- Agent workflow：happy path 测试

## 详见

- [agent/CLAUDE.md](app/agent/CLAUDE.md)
- [tools/CLAUDE.md](app/tools/CLAUDE.md)
- [rpa/CLAUDE.md](app/rpa/CLAUDE.md)
- [safety/CLAUDE.md](app/safety/CLAUDE.md)
