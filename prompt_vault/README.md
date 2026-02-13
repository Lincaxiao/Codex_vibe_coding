# Prompt Vault

Prompt Vault 是一个本地优先（local-first）的提示词管理工具，提供 Python 库与命令行接口，便于你每天离线维护、检索、渲染和导入导出提示词。

## 为什么有用

- 所有数据保存在本地 SQLite，离线可用。
- 支持标题/正文/标签搜索。
- 支持 `{{placeholder}}` 模板渲染。
- 支持软删除，避免误删即丢。
- 支持 JSON / Markdown 导出与 JSON 导入去重。
- 支持桌面 GUI（Tkinter）与可打包为 Windows 程序（EXE）。

## 快速开始（零安装）

在仓库根目录执行：

```bash
python -m prompt_vault init
python -m prompt_vault add --title "日报总结" --body "请总结 {{date}} 的工作进展"
python -m prompt_vault list
```

## GUI 启动（推荐）

在仓库根目录执行：

```bash
python -m prompt_vault gui
```

或直接运行：

```bash
prompt_vault/scripts/run_gui.bat
```

## 常用命令示例

### add

```bash
python -m prompt_vault add --title "代码审查" --body "请用要点审查以下代码：{{code}}"
```

### list

```bash
python -m prompt_vault list
python -m prompt_vault list --all
```

### show

```bash
python -m prompt_vault show 1
```

### search

```bash
python -m prompt_vault search 审查
python -m prompt_vault search python
```

### edit

```bash
python -m prompt_vault edit 1 --title "代码审查助手"
python -m prompt_vault edit 1 --body "请从可读性、性能、安全性审查：{{code}}"
```

### delete（软删除）

```bash
python -m prompt_vault delete 1
```

### tag

```bash
python -m prompt_vault tag 1 --add python --add review
python -m prompt_vault tag 1 --remove review
```

### render

```bash
python -m prompt_vault render 1 --var code='print("hi")'
python -m prompt_vault render 1 --vars-json prompt_vault/examples/vars.json
```

### clip

```bash
python -m prompt_vault clip 1
python -m prompt_vault clip 1 --var code='print("hi")'
```

### export

```bash
python -m prompt_vault export --format json --output prompt_vault/exports/prompts.json
python -m prompt_vault export --format markdown --output prompt_vault/exports/prompts.md
```

### import

```bash
python -m prompt_vault import --input prompt_vault/exports/prompts.json
```

## 数据位置与安全说明

- 默认数据库位置：`prompt_vault/data/prompt_vault.sqlite`
- 你也可以通过 `--db` 指定其他数据库文件。
- 软删除仅标记 `is_deleted=1`，不会物理删除数据。
- 工具不包含破坏性批量清理操作。
- 所有读写都限制在本地文件系统，不依赖远程网络服务。

## 运行测试

从仓库根目录执行：

```bash
bash prompt_vault/scripts/test.sh
```

在 Windows 下也可直接执行：

```bash
python -m unittest discover -s prompt_vault/tests -v
```

## 打包为程序（Windows EXE）

安装 `pyinstaller` 后执行：

```bash
prompt_vault/scripts/build_exe.bat
```

输出目录：`prompt_vault/dist/PromptVault/`

## 作为库使用

```python
from pathlib import Path
from prompt_vault.db import PromptDB
from prompt_vault.service import render_template

db = PromptDB(Path("prompt_vault/data/prompt_vault.sqlite"))
db.init()
prompt_id = db.add_prompt("问候", "你好 {{name}}")
record = db.get_prompt(prompt_id)
print(render_template(record.body, {"name": "世界"}))
```
