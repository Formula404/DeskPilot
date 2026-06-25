# rpa — 桌面 RPA 能力

提供底层感知和执行能力：截图、OCR、模板匹配、鼠标键盘操作、窗口控制。RPA 是兜底方案，不是默认路径。

## 执行链路

```
截图 → 预处理 → OCR/模板匹配/UIA 查询 → 定位目标
  → 执行动作 → 再截图 → 校验结果
```

## 执行策略优先级

1. **UI Automation (UIA)** — 最优先，通过控件树找元素
2. **OCR / 模板匹配** — 当 UIA 不可用时使用
3. **坐标点击** — 最后兜底

## 坐标规则

- **必须使用窗口相对坐标**，禁止写死全屏绝对坐标
- 优先使用图像锚点定位
- DPI 缩放和主题变化必须可处理

## 核心动作

- 启动应用
- 激活窗口
- 截图（mss）
- OCR（PaddleOCR）
- 模板匹配（opencv-python）
- 鼠标点击、移动（pyautogui）
- 键盘输入、快捷键（pyautogui）
- 滚动
- 等待界面变化
- 验证操作结果

## 约束

- 每个动作必须有**超时**
- 每个动作必须支持**取消**
- 每个 RPA workflow 必须有**最大步数**
- 敏感操作执行前必须请求用户**确认**
- RPA 截图默认只保存到任务目录，**不能写入长期记忆**
- 不直接读取应用加密数据或本地数据库
- 不做完就认为成功，必须校验

## 文件组织

```
rpa/
  screenshot.py    # mss 截图
  ocr.py           # PaddleOCR 封装
  vision.py        # opencv 模板匹配、图像预处理
  input.py         # pyautogui 鼠标键盘
  window.py        # pywin32 窗口操作
  uia.py           # pywinauto UI Automation
```

## 第一阶段

RPA 模块第一版只保留目录和接口，不做完整实现。第一阶段不需要 OCR、pyautogui、PaddleOCR。

## 依赖

- 依赖：无（只依赖基础库）
- 不可依赖：`api`、`agent`
