# FocusLog 现代化 GUI 重构计划（React + Python + PyWebView，跨平台）

## Summary
本次重构目标是“一步到位”替换当前 Tk GUI，交付现代感、跨平台（Windows/macOS）的桌面应用形态，同时保留现有本地 SQLite 与 CLI 能力。

### 已确认根因
1. **分辨率和字体发糊**：当前 Tk GUI 在高 DPI / 系统缩放场景下容易走传统缩放路径，视觉清晰度与像素对齐不足。
2. **视觉风格陈旧**：界面基于 `tkinter + ttk` 默认主题，缺少现代设计系统（tokens、间距体系、层级、状态色与动效规范）。

### 决策结论
- 技术路线：**React 前端 + Python 后端 + 桌面壳**
- 改造节奏：**一步到位重构**
- 桌面壳：**PyWebView**
- 第一版范围：**GUI 全量平替**
- 视觉方向：**专业简洁（浅色主导）**
- 平台目标：**Windows + macOS**

---

## Scope

### 包含
- 重做 GUI 为 Web 前端并嵌入 PyWebView。
- 新增本地 HTTP API（FastAPI）承接全部 GUI 功能。
- 保持 CLI 现有命令行为不变。
- 保持 SQLite 数据模型与数据路径不变（`focuslog/data/focuslog.sqlite`）。
- 提供 Windows/macOS 的构建与运行脚本。
- 保留本地离线运行能力，不引入在线依赖。

### 不包含
- 云同步、账号系统、在线服务。
- 移动端。
- 多语言国际化（第一版默认中文）。

---

## Architecture（定版）

- **前端**：React + TypeScript + Vite
- **状态与数据**：TanStack Query + React Hook Form
- **样式**：Tailwind CSS + 自定义 Design Tokens（浅色主导）
- **后端**：FastAPI + Pydantic
- **桌面壳**：PyWebView
- **核心逻辑复用**：`FocusLogDB`、`timer.py`、`reporting.py`、`exporting.py`、`notifier.py`

### 目录建议

```text
focuslog/
  app_entry.py                # 兼容入口（保留）
  __main__.py
  cli.py                      # CLI 保持不变
  db.py
  timer.py
  reporting.py
  exporting.py
  notifier.py

  desktop/
    main.py                   # 启动 FastAPI + PyWebView
    window.py                 # 窗口与生命周期

  api/
    app.py                    # FastAPI app
    schemas.py                # Pydantic 模型
    routes/
      timer.py
      sessions.py
      stats.py
      report.py
      export.py
      health.py

  web/
    (React + TS + Vite 工程)
```

---

## API 设计（v1）

> 目标：覆盖现有 Tk GUI 的全部能力，并为后续扩展（例如番茄历史筛选、批量标签）留接口空间。

### Timer
- `POST /api/v1/timer/start`：启动计时任务。
- `POST /api/v1/timer/stop`：请求停止（优雅中断）。
- `GET /api/v1/timer/state`：查询当前运行状态。
- `GET /api/v1/timer/stream`：SSE 推送 tick / 阶段切换 / 完成事件。

### Sessions
- `GET /api/v1/sessions`：分页查询日志（支持 since/tag/task_contains/limit）。
- `GET /api/v1/sessions/{id}`：单条会话详情。

### Stats / Report / Export
- `GET /api/v1/stats`：今天/本周/最近7天统计。
- `POST /api/v1/report/weekly`：生成周报并返回文件路径。
- `POST /api/v1/export/csv`：导出 CSV 并返回文件路径。

### System
- `GET /api/v1/health`：健康检查。
- `GET /api/v1/meta`：版本、数据库路径、平台信息。

---

## 前端信息架构（IA）

- **Dashboard（首页）**
  - 当前阶段、倒计时、开始/停止、快速配置。
  - 最近一次中断原因与完成状态。
- **Sessions（日志）**
  - 表格 + 过滤（标签、任务关键字、时间范围）。
  - 快速查看会话详情。
- **Stats（统计）**
  - 今天 / 本周 / 最近7天卡片。
  - 工作/休息占比、完成率。
- **Report & Export（产出）**
  - 一键生成周报、导出 CSV。
  - 输出目录与结果提示。
- **Settings（设置）**
  - 默认番茄参数、提示音、通知策略。

---

## UX / 视觉规范（首版）

- 浅色主题优先，支持后续扩展暗色主题。
- 8pt 间距体系、语义化颜色（primary/success/warning/danger）。
- 明确状态层级：空闲、进行中、暂停/中断、完成。
- 倒计时数字使用等宽字体并保证高对比度。
- 全局键盘可达性（Tab 顺序、按钮焦点态、Enter 快捷提交）。
- 错误反馈统一为 Toast + 可展开详情。

---

## 兼容性与迁移策略

- 数据库不迁移：继续使用 `FocusLogDB` 既有 schema。
- CLI 保持原样：`start/log/stats/report/export` 行为不变。
- GUI 切换策略：
  1. 新增 `desktop` 入口（并行验证）；
  2. 验收通过后将 `gui` 命令默认指向 PyWebView 版；
  3. 保留 Tk 版本一段观察期后移除。

---

## 里程碑（建议）

### M1：后端 API 骨架（1 周）
- FastAPI 工程落地、健康检查、stats/log/report/export 打通。

### M2：计时核心接入（1 周）
- start/stop/state + SSE 事件流。
- 与 `PomodoroRunner` 的线程/状态管理适配。

### M3：前端主界面（1~2 周）
- Dashboard/Sessions/Stats 页面。
- 基础设计系统、表单校验、错误处理。

### M4：桌面壳联调与打包（1 周）
- PyWebView 窗口生命周期。
- Windows/macOS 打包脚本。

### M5：回归验收与切换（0.5~1 周）
- CLI 回归、数据一致性验证。
- gui 命令切换与发布说明。

---

## 验收标准（DoD）

- 在 Windows/macOS 上可离线运行。
- GUI 功能覆盖现有 Tk 版（启动/停止、状态、日志、统计、周报、CSV）。
- 默认数据库路径与历史数据可直接复用。
- CLI 全量命令回归通过。
- 关键交互响应时间满足：
  - start/stop ≤ 300ms（本地）；
  - stats/log 查询 ≤ 500ms（中等数据量）。

---

## 风险与对策

1. **计时线程与 API 并发状态不一致**
   - 对策：引入单例 `TimerService` + 显式状态机（idle/running/stopping/finished）。
2. **SSE 在桌面壳中的重连稳定性**
   - 对策：前端实现指数退避重连 + 心跳事件。
3. **通知能力跨平台差异**
   - 对策：继续“尽力而为”策略，失败退回应用内提示。
4. **打包体积增长**
   - 对策：前端静态资源压缩、清理未使用依赖、分平台构建配置。

---

## 与 Prompt Vault 升级路线对齐点

- 同样采用 React + FastAPI + PyWebView 的三层结构。
- 同样坚持离线优先 + 本地 SQLite + CLI 稳定。
- 同样采用“一步到位重构 GUI”，并通过 API 复用现有核心业务逻辑。

