# agent — LangGraph 编排核心

采用 "Manager + Agents as Tools + 确定性执行边界" 的 Agent 模式。

## 架构原则

- Manager 理解完整目标、解析指代、生成跨领域委派依赖，并拥有最终回复。
- Tool calling 必须是受限白名单：每个专业 Agent 只暴露本领域低风险或已授权工具。
- LangGraph 负责状态、步数、权限、安全节点、失败兜底和最终收束，不把业务步骤全部写死。
- Tool calling 循环有最大步数限制。
- 固定 workflow 只作为兜底和强约束任务使用，不能作为普通任务的唯一执行方式。

## 图结构

```
冻结上下文 → 构造 ManagerContext → Manager 结构化理解
  → 澄清 / 直接回复 / 专业 Agent 委派
  → 领域 Tool Calling → observation / artifact → Manager
  → Manager 统一回答 → memory policy
```

## 状态定义 (AgentState)

```python
user_input: str           # 用户原始指令
desktop_context: dict     # 当前窗口、应用、URL、截图信息
manager_context: dict     # Manager 轻量上下文
intent_understanding: dict # 多领域、操作、目标、约束和澄清
delegations: list         # 带依赖的专业 Agent 委派记录
tool_calls: list          # 已调用和待调用工具
observations: list        # 工具返回结果
risk_level: str           # low / medium / high
requires_confirmation: bool
memory_refs: list         # 检索到的记忆
approval_state: dict      # 审批状态
final_response: str       # 最终反馈
```

## 稳定语义维度

- Domain：`web` / `knowledge` / `file` / `desktop` / `conversation`
- Operation Class：`read` / `search` / `extract` / `transform` / `create` / `save` / `update` / `delete` / `open` / `communicate` / `inspect` / `approve`
- Goal 保留自然语言摘要，具体 Capability 从 Tool Registry 动态发现。
- `detect_intent()` 只作为模型完全不可用时的有限兼容降级，禁止作为正常路由。

## 执行策略优先级

1. 官方 API / 本地 API
2. CLI / URI Scheme / 快捷命令
3. 浏览器扩展通道操作用户当前页（collect/click/type/extract）
4. Playwright 受控浏览器自动化（独立浏览器任务和测试）
5. Windows UI Automation (UIA)
6. 图像识别 / OCR / 坐标点击（RPA 兜底）

## 约束

- 任务必须先经过 Manager 结构化理解，不允许由用户直接指定低层工具
- LLM 只允许调用当前任务白名单里的工具
- 每次工具调用前必须经过权限检查（调用 safety 模块）
- 每次工具调用后必须产生 observation
- 每次 tool call 和 observation 必须写入 task_steps，便于审计和面试展示
- 敏感任务必须进入 approval 节点
- **禁止** Agent 直接执行任意 Python、PowerShell、cmd 或 shell 字符串
- **禁止** 让 LLM 直接拼接系统命令
- **禁止** 绕过 safety 层直接调用工具
- 网页任务必须通过结构化浏览器工具调用扩展通道或 Playwright，禁止让 LLM 直接生成任意页面脚本执行

## 文件规范

- `state.py` — Agent state TypedDict/Pydantic 定义
- `graph.py` — LangGraph 图构建
- `nodes.py` — 各节点实现
- `intents.py` — 兼容分类器和有限安全降级（不参与正常路由）
- `tool_calling.py` — OpenAI tool calling 循环、工具 schema 映射、observation 处理
- `prompts.py` — LLM 提示词（如有需要）

## 依赖

- 依赖：`tools`、`safety`、`memory`、`schemas`
- 不可被依赖：`api`、`frontend`
