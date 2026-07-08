# frontend — Tauri 悬浮窗

Tauri + React + Vite + TypeScript，多窗口桌面悬浮助手。

## 技术栈

| 用途 | 技术 |
|---|---|
| 框架 | React + Vite |
| 语言 | TypeScript strict mode |
| 状态管理 | Zustand |
| 样式 | 自定义 CSS（CSS 变量 + 玻璃质感公共模式） |
| 动效 | GSAP + @gsap/react + Flip |
| 桌面壳 | Tauri |
| 通信 | HTTP + SSE 连接本地 FastAPI |

## 为什么用自定义 CSS 而非 Tailwind

本项目的视觉风格是暗色玻璃质感，核心效果依赖 Tailwind 无法表达的特性：

- 多层 `::before` / `::after` 伪元素渐变边框
- 精确 `backdrop-filter: blur() saturate()` 数值
- 复杂 `radial-gradient` + `linear-gradient` 叠加

用 Tailwind 会导致 `@layer components` 里写同样的自定义 CSS + `tailwind.config.js` 塞满 arbitrary values，反而更乱。因此本项目**统一使用自定义 CSS**，禁止在组件中混用 Tailwind 工具类。

## 目录结构

```
frontend/src/
  api/          # 后端 HTTP 请求封装（统一走这里，组件不直接拼 URL）
  assets/       # 图标等静态资源
  hooks/        # 通用 React hooks
    useWindowLifecycle.ts  # 窗口生命周期（失焦关闭、Escape、入场/出场动效）
  motion/       # GSAP 动效系统
    register.ts       # GSAP + useGSAP + Flip 注册
    constants.ts      # 动效时长、缓动、stagger 预设
    useReducedMotion.ts  # prefers-reduced-motion 媒体查询 hook
  store/        # Zustand stores
  styles/       # 样式
    tokens.css        # CSS 变量（颜色、圆角、阴影、动效时长）
    glass.css         # 玻璃质感公共模式（pill、card、composer 等）
    components.css    # 各视图组件样式
  types/        # TypeScript 类型定义
  views/        # 按窗口拆分的视图组件（每个视图一个文件）
    FloatingBall.tsx  # 悬浮球
    ContextMenu.tsx   # 右键菜单
    Overlay.tsx       # 全屏覆盖层（含建议按钮区、状态消息）
    CommandComposer.tsx  # 命令输入框
    TaskPanel.tsx     # 任务执行步骤面板
    Settings.tsx      # 设置页
  App.tsx       # 根组件（~30 行），只做窗口 label 路由
```

## CSS 变量体系

所有颜色、圆角、阴影统一通过 `styles/tokens.css` 中的 CSS 变量定义，禁止在组件样式中硬编码 hex 值：

```css
:root {
  --color-accent: #2d6df6;
  --color-accent-ring: rgba(45, 109, 246, 0.34);
  --color-success: #35a852;
  --color-danger: #ef4444;
  --glass-border: rgba(202, 219, 255, 0.42);
  --glass-bg: linear-gradient(135deg, rgba(255,255,255,0.18), ...);
  --glass-shadow: 0 14px 34px rgba(42, 91, 181, 0.16), ...;
  --radius-pill: 999px;
  --radius-card: 14px;
}
```

## 多窗口架构

Tauri 配置了 4 个独立窗口，每个窗口加载同一前端但根据 `Window.getCurrent().label` 渲染不同视图：

| 窗口 label | 视图组件 | 尺寸 | 特点 |
|---|---|---|---|
| `floating-ball` | `FloatingBallView` | 132×132 | 无边框、透明、置顶、可拖拽 |
| `context-menu` | `ContextMenuView` | 188×178 | 无边框、透明、置顶、失焦自动隐藏 |
| `overlay` | `OverlayView` | 全屏 | 无边框、透明、置顶、点击空白处关闭 |
| `settings` | `SettingsView` | 860×600 | 无边框、非置顶、可缩放 |

## 动效系统

- 所有 UI 动效使用 GSAP（GreenSock Animation Platform）
- `motion/constants.ts` 定义了统一的 duration、ease、stagger 预设
- `getMotionDuration(duration, reduceMotion)` 在 reduced-motion 模式下将 duration 降为 0.01s
- `useReducedMotion()` hook 监听 `prefers-reduced-motion: reduce` 媒体查询
- CSS 也通过 `@media (prefers-reduced-motion: reduce)` 关闭所有 transition
- 每个视图组件在打开时播放入场动效，关闭时播放出场动效

## 视图组件规范

每个视图组件遵循统一模式，公共逻辑由 `hooks/useWindowLifecycle` 承载：

- **窗口生命周期**：`useWindowLifecycle(label, { onOpen, onClose })` 自动处理：
  - `onFocusChanged` 监听（失焦关闭 / 聚焦重播入场动效）
  - Escape 键关闭
  - 防重入（`closingRef`）
  - 出场动效 → `hideCurrentWindow()` → 重置 motion targets
- **入场/出场动效**：每个视图定义 `playOpenMotion()` 和 `closeWithMotion()`，内部通过 `gsap.timeline()` 编排
- **重置函数**：每个视图定义 `resetMotionTargets()`，在关闭后清除 GSAP 状态避免下次打开时残留

**禁止的做法：**

- 禁止在多个视图组件中复制粘贴 `closingRef`、`onFocusChanged`、Escape 监听等重复逻辑
- 禁止在组件中直接拼接 URL 或裸调 fetch，统一走 `api/` 模块
- 禁止在 CSS 中硬编码颜色 hex 值，必须用 CSS 变量

## 约束

- **禁止** 直接调用 OpenAI SDK 或任何 AI API
- **禁止** 直接访问 SQLite 或任何数据库
- **禁止** 直接执行本机自动化（pyautogui、RPA 等）
- Zustand store 只保存 UI 状态、任务状态和设置，不保存大段敏感内容

## 通信

- 提交任务：`POST /chat`
- 取消任务：`POST /tasks/{id}/cancel`
- 任务状态：`GET /tasks/{id}`
- 实时事件：`GET /events` (SSE)
- 审批：`POST /approvals/{id}`

## 构建

```bash
npm run dev     # 开发
npm run build   # 生产构建
```
