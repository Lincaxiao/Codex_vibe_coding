# plan.md — Mac 本地 GUI 课程笔记 Agent（纯 Codex，本机执行）

## 1. 摘要

本项目交付一个仅面向 macOS 的本地桌面 GUI 工具，用于课程笔记多轮自动生成与最终人工审阅。
模型调用仅使用本机 `codex exec`，不使用反代、不接入 opencode、不依赖 Codex Cloud 读取本地路径。
支持“多课程工作区”：在一个总目录下管理多门课程，每门课有独立课程子文件夹与独立笔记子文件夹。
每门课对应一个独立 `project_root`，保存快照、中间态、运行日志与可追溯产物；笔记落到该课程对应 `notes_root`。
默认 Round1/2/3 自动执行，用户仅在 Final 轮参与；支持可选“每轮暂停”和“大改动自动暂停”。

## 2. 关键决策（先锁死）

1. 执行位置：仅本机执行，主路径是本地 `codex exec`，不把“读取任意本地路径”需求放到云端。
2. GUI 形态：v1 采用 Python 原生桌面 GUI（PySide6/Qt），用原生文件选择框选目录和文件。
3. 技术栈：v1 单语言 Python（GUI + 编排 + 检查），降低 React + FastAPI 双栈复杂度。
4. 多课程组织：支持在一个总目录下按课程创建子目录，课程之间隔离执行与产物。
5. 源文件保护：采用“源资料快照 + 哈希 + 只读权限”机制，禁止直接写课程原目录。
6. 无命令行交互：运行中不允许出现等待批准的交互挂起，失败必须可恢复。
7. 网络策略：默认禁网，仅 Final 阶段可选“扩展阅读”并单独标注来源。

## 3. 范围与硬约束

1. 所有生成笔记必须是中文。
2. 不修改课程源码与 slide 原文件。
3. 用户可从任意本地路径选择素材与输出目录。
4. 中间态保存到 `project_root`，不混入课程原目录。
5. 笔记输出保存到 `notes_root`。
6. 首版只支持 Codex 通道（`codex exec`）。
7. 用户默认仅在 Final 轮人工审阅。
8. review 粒度支持：`section` 或 `lecture`。
9. 用户日常使用不依赖命令行。
10. 支持一个总目录下多门课程并行存在，每门课独立输入/输出子目录。

## 4. 系统架构（v1）

1. GUI 层：PySide6 桌面应用（项目管理、路径选择、运行控制、日志、diff、Markdown 预览、Final 审阅）。
2. 应用服务层：Python Service（ProjectService、SnapshotService、WorkflowOrchestrator、CheckRunner、DiffService）。
3. 执行器：`CodexExecutor`，通过子进程调用 `codex exec`。
4. 状态层：`project.yaml` + `state/*.json` + `runs/<run_id>/*`，支持断点恢复与追溯。
5. 可扩展性：后续若需 Web UI，再评估 pywebview 壳；v1 不引入 React/Node 工具链。

## 5. 工作区与路径映射

1. 可选 `workspace_root`（总目录），用于集中管理多门课程。
2. 每门课使用唯一 `course_id`（建议 slug）作为子目录名。
3. 默认映射（可在 GUI 中覆盖）：
   `<workspace_root>/projects/<course_id>` 作为 `project_root`，
   `<workspace_root>/notes/<course_id>` 作为 `notes_root`。
4. 也支持手工指定任意 `project_root` 与 `notes_root`，不强制固定结构。

## 6. 目录规范

### 6.1 `project_root`（中间态、可追溯、可恢复）

- `<project_root>/project.yaml`
- `<project_root>/state/session.json`
- `<project_root>/state/round_status.json`
- `<project_root>/artifacts/source_index.json`
- `<project_root>/artifacts/source_hashes.json`
- `<project_root>/artifacts/snapshots/<timestamp>/...`
- `<project_root>/runs/<run_id>/prompt.md`
- `<project_root>/runs/<run_id>/codex_stdout.log`
- `<project_root>/runs/<run_id>/codex_last_message.md`
- `<project_root>/runs/<run_id>/check_result.json`
- `<project_root>/runs/<run_id>/run_manifest.json`
- `<project_root>/runs/<run_id>/changes.patch`
- `<project_root>/runs/<run_id>/notes_snapshot/...`（可选，仅保存本轮改动文件）

### 6.2 `notes_root`（用户指定输出）

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

## 7. 核心数据类型

1. `ProjectConfig`：
   `workspace_root?`、`course_id`、`project_root`、`notes_root`、`language=zh-CN`、`review_granularity=section|lecture`、`human_review_timing=final_only`、`pause_after_each_round=false`、`max_changed_lines`、`max_changed_files`、`network_mode=disabled_by_default`。
2. `SourceSelection`：
   `slides_md[]`、`slides_pdf[]`、`code_paths[]`、`lecture_mapping[]`、`snapshot_root`、`source_hashes`。
3. `RunRequest`：
   `target_lectures[]`、`from_round`、`to_round`、`allow_external_refs=false`。
4. `RunManifest`：
   `model`、`codex_cli_version`、`sandbox_mode`、`ask_for_approval_mode`、`network_enabled`、`search_enabled`、`writable_dirs[]`、`retry_count`。
5. `RunResult`：
   `status`、`round_results[]`、`check_results[]`、`errors[]`、`pause_reason`。

## 8. 源资料保护机制（必须实现）

1. 用户选定素材路径后，先执行采集与快照：复制到 `<project_root>/artifacts/snapshots/<timestamp>/`。
2. 计算并落盘哈希到 `source_hashes.json`，建立“原路径 -> 快照路径 -> 哈希 -> lecture 映射”的索引。
3. 快照目录设置为只读权限（文件只读、目录只读遍历）。
4. 每轮结束后再次校验快照哈希，确保流程中无意外写入。
5. Codex 与检查器仅读取快照，不直接读取/写入原始课程目录。

## 9. Codex 执行策略（唯一通道）

1. 执行命令统一为 `codex exec`，每轮使用独立 prompt 模板。
2. 工作目录固定 `project_root`，可写目录仅允许 `project_root` 与 `notes_root`。
3. 运行策略要求“失败可恢复，不等待批准”，避免子进程挂起。
4. 推荐参数策略（以实际 CLI 版本参数名为准）：
   `--cd <project_root> --sandbox workspace-write --add-dir <notes_root> --ask-for-approval never`。
5. `codex login status` 失败时仅提示“请先登录 Codex CLI”，不崩溃。
6. 网络或流式失败自动重试 2 次；超过阈值进入可恢复失败态。
7. `check.sh` 失败时触发一次“仅修复检查失败项”补救轮。
8. 权限失败或越权写入失败时不等待人工批准，直接失败并给出可操作修复建议。

## 10. 网络与外部信息策略

1. 默认禁用网络与外部搜索。
2. Round1/2/3 仅基于本地快照（slides/code）产出内容。
3. Final 提供可选开关“生成扩展阅读/外部参考”。
4. 开启外部参考时，外部内容必须放在独立小节并标注来源链接。
5. 外部引用与本地课程结论必须分区展示，避免混淆来源。

## 11. Round 工作流定义

1. Round0：初始化 `notes_root` 骨架、模板、review 规范、检查脚本。
2. Round1：按 lecture 生成 skeleton 草稿。
3. Round2：扩展可读内容、示例、练习、易错点。
4. Round3：读取 `review/feedback.md`，仅处理未勾选项并写 resolution。
5. Final：更新 `cheatsheet.md`、清洗 `glossary.md`、可选生成 `flashcards.csv`、可选扩展阅读。
6. 全局约束：中文输出、非平凡结论附 `Source:`、TODO 与 backlog 同步。
7. 每轮固定后处理：执行检查、保存 patch、更新 run manifest、可选保存 notes snapshot。

## 12. 检查与门禁（check_notes.py）

1. 结构完整性检查：必需文件、目录、索引存在且格式正确。
2. 引用检查：关键结论带 `Source:`，且可追溯到本地快照或外部链接。
3. 中文比例检查：正文中文占比低于阈值则失败（代码块/标识符/术语白名单豁免）。
4. 术语一致性检查：首次建议“中文（English）”，后续用词保持一致。
5. 反馈闭环检查：Round3 只处理未勾选项，且必须写入 resolution。
6. 不可变性检查：快照哈希前后必须一致。
7. 大改动阈值检查：超出 `max_changed_lines` 或 `max_changed_files` 自动暂停。

## 13. GUI 用户流程

1. 新建或打开工作区项目（可选先选择 `workspace_root`）。
2. 选择或新建 `course_id`（每门课一个子项目）。
3. 通过原生文件选择框选择该课程的 slides/code 路径。
4. 自动生成或手工确认该课程 `project_root` 与 `notes_root`。
5. 执行快照与哈希校验，展示映射结果。
6. 配置粒度与运行策略开关。
7. 点击执行自动轮次（默认 Round1 -> Round2 -> Round3 -> Final）。
8. 实时查看日志、检查结果、diff 与产物预览。
9. 在 Final 页人工审阅并“通过/回改”。
10. 可选“每轮后暂停”与“超阈值自动暂停”，支持中途接管与恢复。

## 14. 失败恢复策略

1. 运行状态：`pending/running/paused/failed_recoverable/failed_blocking/succeeded`。
2. 任何需要批准的操作都不得进入等待态，必须转成失败态并可恢复。
3. 恢复入口：从失败轮次继续，或进入“仅修复失败项”补救轮。
4. 重启后可从 `state/round_status.json` + `runs/<run_id>/` 恢复现场。

## 15. 测试用例

1. 任意本地路径素材 + 任意输出路径，流程跑通。
2. 同一 `workspace_root` 下可创建多门课程子项目，互不污染。
3. 默认子目录映射（`projects/<course_id>` 与 `notes/<course_id>`）正确。
4. 路径选择全程 GUI 完成，无需手工粘贴路径。
5. Round0 初始化后 `check.sh` 通过。
6. Round1/2 产出中文 lecture 草稿并附 `Source:`。
7. Round3 仅处理未勾选反馈并产出 resolution。
8. Final 正常生成 `cheatsheet`，`glossary` 去重规范。
9. Codex 未登录时提示准确且系统不崩溃。
10. 网络异常触发重试并可恢复。
11. 快照哈希前后完全一致，原始课程目录无修改。
12. 强制制造越权写入时，运行快速失败且不出现批准等待挂起。
13. `review_granularity=section|lecture` 行为正确。
14. 开启“每轮暂停”与“大改动暂停”时控制逻辑正确。

## 16. 分阶段实现（按小 PR 交付）

1. PR1：项目骨架 + `project/state/runs` 基础结构 + 创建项目与配置保存。
2. PR2：Source snapshot + hash 校验 + `source_index/source_hashes`。
3. PR3：`CodexExecutor` 最小可用（执行一轮、落盘 stdout/last_message/manifest）。
4. PR4：Round0 + `check` 脚本 + GUI 一键初始化。
5. PR5：Round1/2/3/Final 最小闭环 + 失败恢复。
6. PR6：diff 预览 + feedback 回写 + 暂停策略（每轮暂停/阈值暂停）。

## 17. 验收标准

1. 用户可仅通过 GUI 完成“多课程目录管理 + 课程笔记生成 + Final 发布”全流程。
2. 流程默认中文输出，且中文要求可被检查器自动验收。
3. 中间态与输出解耦，且每轮有完整可追溯产物。
4. 源资料通过快照机制得到工程级保护，不会被流程污染。
5. 默认 Final 人工审阅，且支持中途接管与可恢复执行。
6. 运行中无命令行交互阻塞，失败可诊断、可恢复。
