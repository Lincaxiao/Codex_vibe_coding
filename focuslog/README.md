# FocusLog

FocusLog 是一个本地优先（local-first）的番茄钟与专注日志工具，当前版本提供：

- Python CLI（稳定）
- 现代化桌面 GUI（React + FastAPI + PyWebView）
- Windows/macOS 打包脚本

## 技术栈

- 后端：`FastAPI + Pydantic`
- 桌面壳：`PyWebView`
- 前端：`React + TypeScript + Vite + Tailwind CSS`
- 数据：`SQLite`（复用现有 `FocusLogDB`）

## 目录结构

```text
focuslog/
  api/
    app.py
    schemas.py
    routes/
  desktop/
    main.py
  frontend/
    src/
    package.json
  cli.py
  gui.py              # 新 GUI 入口（WebView）
  legacy_gui.py       # 旧 Tk GUI（仅回滚）
  app_entry.py        # GUI-first 入口（--cli 保留）
  requirements-gui.txt
  scripts/
    run_gui.bat
    build_web.bat
    build_desktop_win.bat
    build_desktop_mac.sh
```

## 依赖安装

Python（GUI 依赖，推荐使用 `VibeCoding` conda 环境）：

```bash
focuslog/scripts/install_gui_deps.bat
```

手动安装等价命令：

```bash
conda run -n VibeCoding python -m pip install --upgrade pip setuptools wheel
conda run -n VibeCoding python -m pip install --use-pep517 --no-warn-script-location -r focuslog/requirements-gui.txt
```

前端依赖：

```bash
npm --prefix focuslog/frontend install
```

## 快速开始

### GUI（推荐）

```bash
python -m focuslog gui
```

Windows 也可：

```bash
focuslog/scripts/run_gui.bat
```

说明：

- Windows 下 GUI 强制使用 `Edge WebView2` 内核（避免旧内核导致布局退化/字体发糊）。
- 若系统未安装 WebView2 Runtime，请先安装后再启动。
- `run_gui.bat` 默认会重建前端资源；如需跳过可设置 `FOCUSLOG_SKIP_WEB_BUILD=1`。
- `build_web.bat` 默认复用 `frontend/node_modules`；如需强制重装可设置 `FOCUSLOG_NPM_INSTALL=1`。
- GUI 内置四页签：`计时设置`、`计时看板`、`统计与产出`、`日志`，并支持本地记忆配置（localStorage）。
- 快捷键：`Ctrl/Cmd+Enter` 启动计时、`Esc` 停止、`Ctrl/Cmd+R` 刷新、`Ctrl/Cmd+L` 切到日志页。

### CLI

```bash
python -m focuslog start --task "写报告" --tags "深度工作,文档" --work 50 --break 10 --cycles 2
python -m focuslog log --limit 20
python -m focuslog stats
python -m focuslog report
python -m focuslog export
```

## 前端开发模式（可选）

```bash
npm --prefix focuslog/frontend run dev
```

然后在另一个终端：

```bash
set FOCUSLOG_DEV_URL=http://127.0.0.1:5173
python -m focuslog gui
```

## GUI 构建与打包

### 构建前端静态资源

```bash
focuslog/scripts/build_web.bat
```

### Windows 打包

```bash
focuslog/scripts/build_desktop_win.bat
```

兼容旧命令：

```bash
focuslog/scripts/build_exe.bat
```

### macOS 打包

```bash
bash focuslog/scripts/build_desktop_mac.sh
```

## API 概览（本地）

- `GET /api/v1/health`
- `GET /api/v1/meta`
- `GET /api/v1/timer/state`
- `POST /api/v1/timer/start`
- `POST /api/v1/timer/stop`
- `GET /api/v1/timer/stream`（SSE）
- `GET /api/v1/sessions`
- `GET /api/v1/sessions/{id}`
- `GET /api/v1/stats`
- `POST /api/v1/report/weekly`
- `POST /api/v1/export/csv`

## 数据与安全说明

- 默认数据库：`focuslog/data/focuslog.sqlite`
- 可通过 `--db` 指定其他路径
- 所有数据均存储在本地 SQLite
- 桌面通知采用“尽力而为”策略，失败会回退为应用内提示

## 测试

```bash
python -m unittest focuslog.tests.test_api focuslog.tests.test_cli focuslog.tests.test_db focuslog.tests.test_notifier focuslog.tests.test_timer focuslog.tests.test_stats focuslog.tests.test_report
```

若已安装前端依赖，也可运行：

```bash
npm --prefix focuslog/frontend run test
```
