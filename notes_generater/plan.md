# plan.md — Mac GUI 课程笔记 Agent（纯 Codex）

## 1. 摘要

本项目交付一个仅面向 macOS 的本地 GUI 工具，用于课程笔记多轮自动生成与最终人工审阅。
模型调用仅使用 `codex exec`，不使用反代、不接入 opencode。
课程素材路径与笔记输出路径都由用户手工指定，不要求固定目录。
每门课对应一个 `project` 文件夹，保存该课中间态与运行日志。
默认 Round1/2/3 自动执行，用户仅在 Final 轮参与审阅。

## 2. 当前环境与迁移策略（Windows -> macOS）

1. 当前机器是 Windows，仅做规划，不做实现落盘。
2. 实现与运行目标平台是 macOS。
3. 路径处理统一使用 Python `pathlib.Path`，禁止硬编码 `\`。
4. 启动方式为本地后端 + 浏览器 GUI，不要求用户命令行参与日常操作。
5. 用户自行完成 `codex login`；应用仅检测登录状态，不处理登录流程。

## 3. 范围与硬约束

1. 所有生成笔记必须是中文。
2. 不修改课程源码与 slide 源文件。
3. 用户可从任意本地路径手工选择素材。
4. 中间态保存到 `project` 文件夹，不混入课程总目录。
5. 笔记输出保存到用户指定目录。
6. 首版只支持 Codex 通道。
7. 用户默认只在 Final 轮参与内容审阅。
8. review 粒度支持可选：`section` 或 `lecture`。

## 4. 系统架构

1. 前端：React GUI（项目管理、素材选择、运行控制、Final 审阅）。
2. 后端：FastAPI（本地 API，编排工作流，执行 Codex，运行检查）。
3. 执行器：`CodexExecutor`，通过子进程调用 `codex exec`。
4. 编排器：`WorkflowOrchestrator`，顺序执行 Round0/1/2/3/Final。
5. 检查器：`CheckRunner`，每轮后运行 `scripts/check.sh`。
6. 状态层：Project 状态文件 + run 日志文件（可中断恢复、可追溯）。

## 5. 目录规范

### 5.1 Project 目录（中间态）

- `<project_root>/project.yaml`
- `<project_root>/state/session.json`
- `<project_root>/state/round_status.json`
- `<project_root>/runs/<run_id>/prompt.md`
- `<project_root>/runs/<run_id>/codex_stdout.log`
- `<project_root>/runs/<run_id>/codex_last_message.md`
- `<project_root>/runs/<run_id>/check_result.json`
- `<project_root>/artifacts/source_index.json`

### 5.2 笔记输出目录（用户指定）

- `<notes_root>/index/manifest.yml`
- `<notes_root>/index/questions_backlog.md`
- `<notes_root>/index/glossary.md`
- `<notes_root>/notes/lectures/*.md`
- `<notes_root>/notes/cheatsheet.md`
- `<notes_root>/notes/flashcards.csv`（可选）
- `<notes_root>/review/feedback.md`
- `<notes_root>/review/rubric.md`
- `<notes_root>/scripts/check_notes.py`
- `<notes_root>/scripts/check.sh`

## 6. 公共接口（Backend API）

1. `POST /api/projects`：创建 project。
2. `GET /api/projects`：列出 project。
3. `POST /api/projects/{id}/config`：保存 `project_root`、`notes_root`、粒度等配置。
4. `POST /api/projects/{id}/sources`：保存手工素材路径与 lecture 映射。
5. `POST /api/projects/{id}/initialize`：执行 Round0 scaffold。
6. `POST /api/projects/{id}/run`：执行 Round1/2/3/Final。
7. `POST /api/projects/{id}/run/{run_id}/resume`：失败后恢复。
8. `GET /api/projects/{id}/runs/{run_id}`：获取进度与日志。
9. `POST /api/projects/{id}/final-review/approve`：Final 通过。
10. `POST /api/projects/{id}/final-review/request-changes`：Final 反馈并重跑。

## 7. 核心数据类型

1. `ProjectConfig`：`project_root`、`notes_root`、`language=zh-CN`、`review_granularity=section|lecture`、`human_review_timing=final_only`。
2. `SourceSelection`：`slides_md[]`、`slides_pdf[]`、`code_paths[]`、`lecture_mapping[]`。
3. `RunRequest`：`target_lectures[]`、`from_round`、`to_round`。
4. `RunResult`：`status`、`round_results[]`、`check_results[]`、`errors[]`。

## 8. Codex 执行策略（唯一通道）

1. 执行命令：`codex exec`。
2. 每轮使用独立 prompt 模板文件，模板变量由后端填充。
3. 每轮执行后必须运行 `scripts/check.sh`。
4. `codex login status` 失败时仅提示“请先登录 Codex CLI”。
5. 网络或流式失败自动重试 2 次。
6. `check.sh` 失败时触发一次“仅修复检查失败项”补救轮。

## 9. Round 工作流定义

1. Round0：创建骨架结构、模板、review 规范、检查脚本。
2. Round1：按 lecture 生成 skeleton 草稿。
3. Round2：扩展可读内容、示例、练习、易错点。
4. Round3：读取 `review/feedback.md`，只处理未勾选项。
5. Final：更新 `cheatsheet.md`、清洗 `glossary.md`、可选生成 `flashcards.csv`。
6. 全局约束：输出中文、非平凡结论附 `Source:`、TODO 与 backlog 同步。

## 10. GUI 用户流程

1. 新建或打开 project。
2. 手工选择 slides/code 路径。
3. 手工选择笔记输出目录。
4. 配置 review 粒度（section 或 lecture）。
5. 点击执行自动轮次。
6. 查看实时日志与每轮检查结果。
7. 在 Final 页进行人工审阅并发布或回改。

## 11. 测试用例

1. 任意路径素材 + 任意路径输出，流程可跑通。
2. Round0 生成结构后 `check.sh` 通过。
3. Round1/2 产出中文 lecture 草稿，含 `Source:`。
4. Round3 仅处理未勾选反馈并写 resolution。
5. Final 生成 `cheatsheet` 且 `glossary` 去重规范。
6. `review_granularity=section` 与 `lecture` 行为正确。
7. Codex 未登录时提示准确且系统不崩溃。
8. 网络异常触发重试并可恢复。
9. 素材文件在流程前后哈希一致（未被改动）。

## 12. 验收标准

1. 用户可仅通过 GUI 完成课程笔记工作流。
2. 笔记默认中文，支持多轮自动优化。
3. project 中间态与笔记输出解耦。
4. 默认仅 Final 轮人工审阅。
5. 每轮均自动检查并保留可追溯日志。

## 13. 假设与默认值

1. 用户已在本机安装并登录 Codex CLI。
2. 首版仅支持 macOS。
3. 素材导入为手工选择，不做自动扫描。
4. `flashcards.csv` 为可选产物，默认开启。
5. 不实现 opencode 或其他模型后端。
