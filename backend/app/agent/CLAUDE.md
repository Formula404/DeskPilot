# agent — LangGraph 编排核心

采用"意图识别 + Workflow 主干 + 受限 ReAct 子循环"的混合模式。

## 架构原则

- 已知高频任务走固定 workflow（可靠、可预测）
- 未知/半开放任务走受限 ReAct（灵活但有边界）
- Workflow 内部可嵌 ReAct 子循环（用于定位、重试等不确定步骤）
- ReAct 子循环最大步数固定为 **5 步**

## 图结构

```
收集上下文 → 意图识别 → workflow 路由 → 选择执行策略
  → 风险评估 → 需要确认? → 等待用户确认 → 执行工具
  → 观察结果 → 是否完成? → 完成总结 / 重新规划
```

## 状态定义 (AgentState)

```python
user_input: str           # 用户原始指令
desktop_context: dict     # 当前窗口、应用、URL、截图信息
intent: str               # 识别后的任务意图
plan: list                # 步骤计划
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
3. Playwright 浏览器 DOM 自动化
4. Windows UI Automation (UIA)
5. 图像识别 / OCR / 坐标点击（RPA 兜底）

## 约束

- 任务必须先经过意图路由，不允许跳过
- 每次工具调用前必须经过权限检查（调用 safety 模块）
- 每次工具调用后必须产生 observation
- 敏感任务必须进入 approval 节点
- **禁止** Agent 直接执行任意 Python、PowerShell、cmd 或 shell 字符串
- **禁止** 让 LLM 直接拼接系统命令
- **禁止** 绕过 safety 层直接调用工具

## 文件规范

- `state.py` — Agent state TypedDict/Pydantic 定义
- `graph.py` — LangGraph 图构建
- `nodes.py` — 各节点实现
- `intents.py` — 意图路由逻辑
- `prompts.py` — LLM 提示词（如有需要）

## 依赖

- 依赖：`tools`、`safety`、`memory`、`schemas`
- 不可被依赖：`api`、`frontend`
