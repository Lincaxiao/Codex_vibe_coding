# FocusLog

FocusLog 是一个离线优先的番茄钟程序，支持命令行与图形界面两种使用方式，包含本地日志、统计、周报和 CSV 导出。

## 环境要求

- Conda 环境：`VibeCoding`
- Python：`3.12`
- 运行时仅使用标准库（SQLite、tkinter 等），不依赖网络

## 快速开始

1. 激活环境：`conda activate VibeCoding`
2. 在仓库根目录查看帮助：`python -m focuslog --help`

### 图形界面（推荐）

```bash
python -m focuslog gui
```

### 命令行番茄钟

```bash
python -m focuslog start --task "论文阅读" --tags "学习,研究" --work 25 --break 5 --long-break 15 --cycles 4 --notify
```

## 常用工作流（CLI）

### 1) 开始番茄钟

```bash
python -m focuslog start --task "写报告" --tags "深度工作,文档" --work 50 --break 10 --cycles 2 --no-sound
```

### 2) 查看最近日志

```bash
python -m focuslog log --limit 20
python -m focuslog log --since 2026-02-10 --tag 深度工作
python -m focuslog log --task-contains 报告
```

### 3) 查看统计（今天 / 本周 / 最近7天）

```bash
python -m focuslog stats
```

### 4) 生成周报 Markdown

```bash
python -m focuslog report
python -m focuslog report --year 2026 --week 7
```

默认输出到：`focuslog/out/week-YYYY-WW.md`

### 5) 导出 CSV

```bash
python -m focuslog export
```

默认输出到：`focuslog/out/focuslog.csv`


## GUI 现代化升级计划（React + FastAPI + PyWebView）

已新增 FocusLog 的完整重构方案文档，路线与 Prompt Vault 保持一致：

- 一步到位替换 Tk GUI
- React + TypeScript + Vite 前端
- FastAPI 本地 API
- PyWebView 桌面壳（Windows/macOS）
- 保持现有 SQLite 与 CLI 行为不变

详见：`focuslog/UPGRADE_PLAN.md`


### 第一阶段已落地（可运行骨架）

当前仓库已提供首批实现：

- `focuslog/api/`：FastAPI 路由（health/meta/sessions/stats/report/export/timer，含 `timer/stream` SSE）。
- `focuslog/desktop/`：PyWebView + Uvicorn 桌面入口。
- `python -m focuslog gui --db <path>`：优先尝试新桌面壳并复用指定数据库；依赖缺失时自动回退 Tk GUI。

> 若要体验新桌面壳，请先安装：`pip install fastapi uvicorn pywebview`

## 程序化交付（可执行文件）

如果你希望双击运行，可在本机安装打包工具后生成 EXE（例如 PyInstaller）：

```bash
focuslog/scripts/build_exe.bat
```

说明：
- 这一步是打包阶段需求，不影响 FocusLog 运行时的离线能力。
- 打包后产物在 `focuslog/dist/`，构建中间文件在 `focuslog/build/`。
- 打包后仍使用本地 SQLite 数据库与本地输出目录。

## 数据与安全说明

- 默认数据库：`focuslog/data/focuslog.sqlite`
- 所有记录仅存储在本地 SQLite，不依赖网络
- 默认 SQLite 日志模式为 `MEMORY`（兼容受限环境）；可通过环境变量 `FOCUSLOG_JOURNAL_MODE` 覆盖（如 `WAL`）
- CLI 中 `Ctrl-C` 会优雅中断，并记录一条带中断原因的会话
- GUI 中“停止”按钮会优雅中断，并记录 `手动停止`
- GUI 直接关闭窗口时会先请求停止并等待当前片段落库，再安全退出
- 桌面通知为“尽力而为”；系统不支持时会退回终端提示，不影响计时

## 运行测试

```bash
bash focuslog/scripts/test.sh
```

或直接运行：

```bash
python -m unittest \
  focuslog.tests.test_cli \
  focuslog.tests.test_db \
  focuslog.tests.test_notifier \
  focuslog.tests.test_timer \
  focuslog.tests.test_stats \
  focuslog.tests.test_report
```
