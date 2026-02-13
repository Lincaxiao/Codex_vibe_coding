# Prompt Vault

Prompt Vault 是一个本地优先（local-first）的提示词管理器，核心数据存储在 SQLite。当前版本提供：

- Python CLI（稳定）
- 现代化桌面 GUI（React + FastAPI + PyWebView）
- Windows/macOS 构建脚本

## 技术栈

- 后端：`FastAPI + Pydantic`
- 桌面壳：`PyWebView`
- 前端：`React + TypeScript + Vite + Tailwind CSS`
- 数据：`SQLite`（复用现有 `PromptDB`）

## 目录结构

```text
prompt_vault/
  prompt_vault/
    db.py
    service.py
    api.py
    schemas.py
    webapp.py
    gui.py            # 新 GUI 入口（WebView）
    legacy_gui.py     # 旧 Tk GUI（仅回滚）
  frontend/
    src/
    package.json
  scripts/
    run_gui.bat
    build_web.bat
    build_desktop_win.bat
    build_desktop_mac.sh
  app_entry.py
```

## 依赖安装

Python（GUI 依赖，推荐使用 `VibeCoding` conda 环境）：

```bash
prompt_vault/scripts/install_gui_deps.bat
```

手动安装等价命令：

```bash
conda run -n VibeCoding python -m pip install --upgrade pip setuptools wheel
conda run -n VibeCoding python -m pip install --use-pep517 --no-warn-script-location -r prompt_vault/requirements-gui.txt
```

前端依赖：

```bash
npm --prefix prompt_vault/frontend install
```

说明：

- `proxy_tools` 的构建告警来自上游包历史构建方式，通常不影响运行；本项目安装命令已启用 `--use-pep517` 以减少该类告警。
- `bottle.exe` / `fastapi.exe` 的 PATH 告警不影响 `python -m prompt_vault` 的运行。
- `whatwg-encoding` 的 deprecate 提示来自前端测试链路（`jsdom` 的传递依赖），不影响生产 GUI 打包与运行。

## 快速开始

### CLI

```bash
python -m prompt_vault init
python -m prompt_vault add --title "日报总结" --body "请总结 {{date}} 的工作进展"
python -m prompt_vault list
```

### GUI（推荐）

```bash
python -m prompt_vault gui
```

Windows 也可：

```bash
prompt_vault/scripts/run_gui.bat
```

说明：

- Windows 下 GUI 强制使用 `Edge WebView2` 内核（避免旧内核导致布局退化/字体发糊）。
- 若系统未安装 WebView2 Runtime，请先安装后再启动。
- `run_gui.bat` 默认会重建前端资源；如需跳过可设置 `PROMPT_VAULT_SKIP_WEB_BUILD=1`。
- `build_web.bat` 默认复用 `frontend/node_modules`；如需强制重装可设置 `PROMPT_VAULT_NPM_INSTALL=1`。

### 前端开发模式（可选）

```bash
npm --prefix prompt_vault/frontend run dev
```

然后在另一个终端：

```bash
set PROMPT_VAULT_DEV_URL=http://127.0.0.1:5173
python -m prompt_vault gui
```

## GUI 构建与打包

### 构建前端静态资源

```bash
prompt_vault/scripts/build_web.bat
```

### Windows 打包

```bash
prompt_vault/scripts/build_desktop_win.bat
```

兼容旧命令：

```bash
prompt_vault/scripts/build_exe.bat
```

### macOS 打包

```bash
bash prompt_vault/scripts/build_desktop_mac.sh
```

## API 概览（本地）

- `GET /api/health`
- `GET /api/prompts`
- `GET /api/prompts/{id}`
- `POST /api/prompts`
- `PUT /api/prompts/{id}`
- `DELETE /api/prompts/{id}`
- `POST /api/prompts/{id}/render`
- `POST /api/prompts/{id}/copy`
- `POST /api/import`
- `POST /api/export`

## 常用 CLI 命令

```bash
python -m prompt_vault search 审查
python -m prompt_vault edit 1 --title "代码审查助手"
python -m prompt_vault render 1 --var code='print("hi")'
python -m prompt_vault export --format json --output prompt_vault/exports/prompts.json
python -m prompt_vault import --input prompt_vault/exports/prompts.json
```

## 数据位置与安全说明

- 默认数据库：`prompt_vault/data/prompt_vault.sqlite`
- 可通过 `--db` 指定其他路径
- 软删除为 `is_deleted=1`，不做物理删除
- 全部读写在本地文件系统内完成

## 测试

```bash
python -m unittest discover -s prompt_vault/tests -v
```

如果当前环境禁止 SQLite 写盘，测试会自动 skip，不会误报失败。
