# tools — 工具注册与执行

所有可被 Agent 调用的能力都注册为结构化工具。工具不实现 Agent 逻辑，只负责"接收结构化输入 → 执行 → 返回结构化输出"。

受限 OpenAI tool calling + 本地 Tool Registry：LLM 在当前任务允许的工具白名单中自主选择工具，后端负责校验、执行、记录 observation。

## 工具结构

每个工具必须包含：

| 字段 | 说明 |
|---|---|
| `name` | `domain.action` 格式 |
| `description` | 给 LLM 的能力描述 |
| `input_schema` | JSON Schema，用于 OpenAI tool calling 参数声明 |
| `output_schema` | 返回结构 |
| `risk_level` | `low` / `medium` / `high` |
| `required_permissions` | 所需权限列表 |
| `handler` | 实际执行函数 |
| `observe` | 执行后验证结果的函数 |
| `fallbacks` | 失败后的降级方案（可选） |

OpenAI function name 不使用点号。内部工具名和 OpenAI 工具名需要稳定映射：

```text
browser.collect_current_page -> browser_collect_current_page
file.write_markdown -> file_write_markdown
```

## 命名规范

```
domain.action
```

示例：
- `browser.get_current_page`
- `browser.summarize_current_page`
- `browser.collect_current_page`
- `browser.execute_page_action`
- `browser.export_table_to_xlsx`
- `desktop.get_foreground_window`
- `desktop.open_app`
- `music.netease.play_song`
- `wechat.export_visible_messages`
- `file.write_markdown`
- `file.write_xlsx`

## 工具返回协议

成功：
```json
{
  "ok": true,
  "data": {},
  "message": "",
  "artifacts": [{"type": "file", "path": "data/exports/result.md"}],
  "error": null
}
```

失败：
```json
{
  "ok": false,
  "data": null,
  "message": "human readable reason",
  "artifacts": [],
  "error": {"code": "ERROR_CODE", "detail": {}}
}
```

## 工具注册

- 所有工具必须在 Tool Registry 中注册后才能被 Agent 发现
- 新增工具文件后，在 `registry.py` 中注册
- 工具注册时声明权限和风险等级，由 safety 层校验
- 一个目录不是一个工具；一个注册到 Tool Registry 的 `ToolDefinition` 才是一个工具。
- Tool Registry 是本地执行层，不等同 MCP。OpenAI tool calling 通过 adapter 把 `ToolDefinition` 转换成模型可见的 tools schema。

## 约束

- **禁止** 让 LLM 直接拼接 shell 命令
- **禁止** 在工具中静默吞异常，必须返回结构化错误
- **禁止** 工具直接写长期记忆（由 memory 模块决定）
- 工具输入输出必须是结构化 schema（Pydantic 或 JSON Schema）
- 每个工具 handler 必须有超时控制
- 暴露给 LLM 的工具必须按 intent 做白名单过滤，不能把所有工具一次性暴露。
- 工具返回给 LLM 的 observation 必须控制大小，网页正文等大文本需要截断或摘要化。

## 目录组织

```
tools/
  base.py          # 工具基类
  registry.py      # Tool Registry
  browser/         # 网页相关工具
  file/            # 文件读写工具
  desktop/         # 桌面应用工具
  music/           # 音乐控制工具（第二阶段）
  wechat/          # 微信工具（第四阶段）
```

## 第一批必须实现的工具

- `browser.collect_current_page`（通过浏览器扩展通道主动采集当前页）
- `browser.get_current_page`（读取最近一次浏览器上下文，作为兼容/缓存）
- `browser.summarize_current_page`（兼容/兜底，不作为 tool calling 主路径）
- `file.write_markdown`
- `desktop.get_foreground_window`
- `file.write_xlsx`

第一阶段 `web_page_summary` 只向 LLM 暴露：

- `browser.collect_current_page`
- `file.write_markdown`

LLM 自己生成总结内容，并通过 `file.write_markdown` 保存。

## 浏览器工具约束

- 当前用户浏览器页面的采集和轻量动作优先走浏览器扩展通道。
- Playwright 用于独立受控浏览器任务、自动化测试和扩展无法覆盖的场景。
- 浏览器动作必须是结构化白名单动作，例如 `collect_page`、`click`、`type`、`scroll`、`extract_table`。
- 禁止让 LLM 直接下发任意 JavaScript 到页面执行。

## 依赖

- 依赖：`safety`、`db`（仅记录日志）、`context`、`rpa`
- 不可依赖：`api`、`agent`
