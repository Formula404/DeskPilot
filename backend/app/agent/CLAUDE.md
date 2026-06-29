# agent — LangGraph 编排核心

采用"意图识别 + LangGraph 状态机 + 受限 OpenAI Tool Calling 循环"的 Agent 模式。

## 架构原则

- 已知高频任务先进入对应任务边界，例如网页、文件、桌面应用，但任务内部由 LLM 通过 tool calling 决定下一步工具。
- Tool calling 必须是受限白名单：每个 intent 只暴露相关低风险或已授权工具。
- LangGraph 负责状态、步数、权限、安全节点、失败兜底和最终收束，不把业务步骤全部写死。
- Tool calling 循环最大步数第一版固定为 **5 步**。
- 固定 workflow 只作为兜底和强约束任务使用，不能作为普通任务的唯一执行方式。

## 图结构

```
收集上下文 → 意图识别 → 选择允许的工具集合
  → Tool Calling 循环（LLM 决策 → 工具调用 → observation）
  → 风险评估 / 审批 → 是否完成? → 最终回答 / 失败兜底
```

## 状态定义 (AgentState)

```python
user_input: str           # 用户原始指令
desktop_context: dict     # 当前窗口、应用、URL、截图信息
intent: str               # 识别后的任务意图
plan: list                # LLM 生成或更新的计划
tool_calls: list          # 已调用和待调用工具
observations: list        # 工具返回结果
risk_level: str           # low / medium / high
requires_confirmation: bool
memory_refs: list         # 检索到的记忆
approval_state: dict      # 审批状态
final_response: str       # 最终反馈
```

## 第一版 Intent 分类

- `web_page_summary`
- `web_table_export`
- `web_page_action`
- `desktop_app_open`
- `music_play`
- `wechat_visible_export`
- `file_operation`
- `general_chat`
- `unknown`

## 执行策略优先级

1. 官方 API / 本地 API
2. CLI / URI Scheme / 快捷命令
3. 浏览器扩展通道操作用户当前页（collect/click/type/extract）
4. Playwright 受控浏览器自动化（独立浏览器任务和测试）
5. Windows UI Automation (UIA)
6. 图像识别 / OCR / 坐标点击（RPA 兜底）

## 约束

- 任务必须先经过意图路由，不允许跳过
- LLM 只允许调用当前任务白名单里的工具
- 每次工具调用前必须经过权限检查（调用 safety 模块）
- 每次工具调用后必须产生 observation
- 每次 tool call 和 observation 必须写入 task_steps，便于审计和面试展示
- 敏感任务必须进入 approval 节点
- **禁止** Agent 直接执行任意 Python、PowerShell、cmd 或 shell 字符串
- **禁止** 让 LLM 直接拼接系统命令
- **禁止** 绕过 safety 层直接调用工具
- 网页任务必须通过结构化浏览器工具调用扩展通道或 Playwright，禁止让 LLM 直接生成任意页面脚本执行

## 第一阶段 Tool Calling 范围

`web_page_summary` 不再写死为 `collect -> summarize -> write`。

第一阶段应让 LLM 在受限工具集合中自主完成：

- `browser.collect_current_page`
- `file.write_markdown`

LLM 负责根据用户指令决定先采集网页、再生成总结内容、最后保存 Markdown。`browser.summarize_current_page` 只作为兼容/兜底工具，不作为主路径。

## 文件规范

- `state.py` — Agent state TypedDict/Pydantic 定义
- `graph.py` — LangGraph 图构建
- `nodes.py` — 各节点实现
- `intents.py` — 意图路由逻辑
- `tool_calling.py` — OpenAI tool calling 循环、工具 schema 映射、observation 处理
- `prompts.py` — LLM 提示词（如有需要）

## 依赖

- 依赖：`tools`、`safety`、`memory`、`schemas`
- 不可被依赖：`api`、`frontend`
