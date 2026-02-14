from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .check_runner import CheckRunResult, CheckRunner
from .codex_executor import CodexExecutor, CodexRunRequest, CodexRunResult
from .diff_service import DiffService, DiffSummary
from .project_service import ProjectService
from .round0_initializer import Round0Initializer

RoundName = Literal["round0", "round1", "round2", "round3", "final"]
RUN_ORDER: list[RoundName] = ["round0", "round1", "round2", "round3", "final"]


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _default_workflow_run_id() -> str:
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"workflow_{timestamp}_{uuid.uuid4().hex[:8]}"


@dataclass(frozen=True)
class RoundExecutionResult:
    round_name: RoundName
    status: str
    codex_run_id: str | None
    codex_success: bool | None
    check_passed: bool | None
    repaired: bool
    check_output_path: str | None
    changed_files: int
    changed_lines: int
    patch_path: str | None
    notes_snapshot_path: str | None
    pause_reason: str | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_name": self.round_name,
            "status": self.status,
            "codex_run_id": self.codex_run_id,
            "codex_success": self.codex_success,
            "check_passed": self.check_passed,
            "repaired": self.repaired,
            "check_output_path": self.check_output_path,
            "changed_files": self.changed_files,
            "changed_lines": self.changed_lines,
            "patch_path": self.patch_path,
            "notes_snapshot_path": self.notes_snapshot_path,
            "pause_reason": self.pause_reason,
            "error": self.error,
        }


@dataclass(frozen=True)
class WorkflowRunResult:
    workflow_run_id: str
    status: str
    started_at: str
    finished_at: str
    rounds: list[RoundExecutionResult]
    workflow_result_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_run_id": self.workflow_run_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "rounds": [item.to_dict() for item in self.rounds],
            "workflow_result_path": str(self.workflow_result_path),
        }


class WorkflowOrchestrator:
    def __init__(
        self,
        *,
        project_service: ProjectService | None = None,
        codex_executor: CodexExecutor | None = None,
        check_runner: CheckRunner | None = None,
        round0_initializer: Round0Initializer | None = None,
        diff_service: DiffService | None = None,
    ) -> None:
        self.project_service = project_service or ProjectService()
        self.codex_executor = codex_executor or CodexExecutor()
        self.check_runner = check_runner or CheckRunner()
        self.round0_initializer = round0_initializer or Round0Initializer()
        self.diff_service = diff_service or DiffService()

    def run(
        self,
        *,
        project_root: Path | str,
        from_round: RoundName = "round1",
        to_round: RoundName = "final",
        notes_root: Path | str | None = None,
        target_lectures: list[str] | None = None,
        allow_external_refs: bool = False,
        search_enabled: bool = False,
        max_retries: int = 2,
        workflow_run_id: str | None = None,
        auto_repair_check_failures: bool = True,
        pause_after_each_round: bool | None = None,
        max_changed_lines: int | None = None,
        max_changed_files: int | None = None,
    ) -> WorkflowRunResult:
        started_at = _now_iso()
        root = Path(project_root).expanduser().resolve()
        config = self.project_service.load_project_config(root)
        notes = Path(notes_root).expanduser().resolve() if notes_root else config.notes_root
        pause_after_round = config.pause_after_each_round if pause_after_each_round is None else pause_after_each_round
        changed_lines_limit = config.max_changed_lines if max_changed_lines is None else max_changed_lines
        changed_files_limit = config.max_changed_files if max_changed_files is None else max_changed_files
        workflow_id = workflow_run_id or _default_workflow_run_id()
        workflow_dir = root / "runs" / workflow_id
        workflow_dir.mkdir(parents=True, exist_ok=False)

        rounds = self._select_rounds(from_round=from_round, to_round=to_round)
        round_results: list[RoundExecutionResult] = []
        workflow_status = "succeeded"

        session_path = root / "state" / "session.json"
        round_status_path = root / "state" / "round_status.json"
        session_payload = self._read_json(session_path)
        round_status_payload = self._read_json(round_status_path)
        session_payload["status"] = "running"
        session_payload["current_run_id"] = workflow_id
        session_payload["updated_at"] = _now_iso()
        self._write_json(session_path, session_payload)

        for round_name in rounds:
            round_status_payload[round_name] = "running"
            self._write_json(round_status_path, round_status_payload)
            before_state = self.diff_service.capture_state(notes_root=notes)
            round_artifact_dir = workflow_dir / round_name
            round_artifact_dir.mkdir(parents=True, exist_ok=True)

            if round_name == "round0":
                init_result = self.round0_initializer.initialize(
                    project_root=root,
                    notes_root=notes,
                    course_id=config.course_id,
                )
                self._write_json(round_artifact_dir / "round0_init_result.json", init_result.to_dict())
                check_output_path = round_artifact_dir / "check_result.json"
                check_result = self.check_runner.run(
                    project_root=root,
                    notes_root=notes,
                    output_path=check_output_path,
                )
                after_state = self.diff_service.capture_state(notes_root=notes)
                diff_summary = self.diff_service.write_diff_artifacts(
                    notes_root=notes,
                    before_state=before_state,
                    after_state=after_state,
                    run_dir=round_artifact_dir,
                )
                if not check_result.passed:
                    round_status_payload["round0"] = "failed"
                    workflow_status = "failed_recoverable"
                    round_results.append(
                        RoundExecutionResult(
                            round_name="round0",
                            status="failed",
                            codex_run_id=None,
                            codex_success=None,
                            check_passed=False,
                            repaired=False,
                            check_output_path=str(check_output_path),
                            changed_files=diff_summary.changed_files,
                            changed_lines=diff_summary.changed_lines,
                            patch_path=str(diff_summary.patch_path),
                            notes_snapshot_path=str(diff_summary.notes_snapshot_path),
                            pause_reason=None,
                            error=self._check_error_summary(check_result),
                        )
                    )
                    self._write_json(round_status_path, round_status_payload)
                    break

                pause_reason = self._evaluate_pause(
                    round_name=round_name,
                    diff_summary=diff_summary,
                    pause_after_round=pause_after_round,
                    changed_lines_limit=changed_lines_limit,
                    changed_files_limit=changed_files_limit,
                )
                if pause_reason:
                    round_status_payload["round0"] = "paused"
                    workflow_status = "paused"
                else:
                    round_status_payload["round0"] = "completed"

                round_results.append(
                    RoundExecutionResult(
                        round_name="round0",
                        status="paused" if pause_reason else "completed",
                        codex_run_id=None,
                        codex_success=None,
                        check_passed=True,
                        repaired=False,
                        check_output_path=str(check_output_path),
                        changed_files=diff_summary.changed_files,
                        changed_lines=diff_summary.changed_lines,
                        patch_path=str(diff_summary.patch_path),
                        notes_snapshot_path=str(diff_summary.notes_snapshot_path),
                        pause_reason=pause_reason,
                        error=None,
                    )
                )
                self._write_json(round_status_path, round_status_payload)
                if pause_reason:
                    break
                continue

            prompt = self._build_round_prompt(
                round_name=round_name,
                notes_root=notes,
                target_lectures=target_lectures or [],
                allow_external_refs=allow_external_refs,
            )
            codex_run_id = f"{workflow_id}_{round_name}"
            codex_result = self.codex_executor.run(
                CodexRunRequest(
                    project_root=root,
                    notes_root=notes,
                    prompt=prompt,
                    run_id=codex_run_id,
                    search_enabled=search_enabled,
                    max_retries=max_retries,
                )
            )

            final_run: CodexRunResult = codex_result
            check_result: CheckRunResult | None = None
            repaired = False

            if codex_result.success:
                check_result = self.check_runner.run(
                    project_root=root,
                    notes_root=notes,
                    output_path=codex_result.run_dir / "check_result.json",
                )

                if not check_result.passed and auto_repair_check_failures:
                    repair_prompt = self._build_repair_prompt(
                        round_name=round_name,
                        check_result=check_result,
                        notes_root=notes,
                    )
                    repair_run_id = f"{workflow_id}_{round_name}_repair1"
                    repair_result = self.codex_executor.run(
                        CodexRunRequest(
                            project_root=root,
                            notes_root=notes,
                            prompt=repair_prompt,
                            run_id=repair_run_id,
                            search_enabled=search_enabled,
                            max_retries=max_retries,
                        )
                    )
                    repaired = True
                    final_run = repair_result
                    if repair_result.success:
                        check_result = self.check_runner.run(
                            project_root=root,
                            notes_root=notes,
                            output_path=repair_result.run_dir / "check_result.json",
                        )
                    else:
                        check_result = None

            after_state = self.diff_service.capture_state(notes_root=notes)
            diff_summary = self.diff_service.write_diff_artifacts(
                notes_root=notes,
                before_state=before_state,
                after_state=after_state,
                run_dir=final_run.run_dir,
            )

            if not final_run.success:
                round_status_payload[round_name] = "failed"
                workflow_status = "failed_recoverable"
                round_results.append(
                    RoundExecutionResult(
                        round_name=round_name,
                        status="failed",
                        codex_run_id=final_run.run_id,
                        codex_success=False,
                        check_passed=None,
                        repaired=repaired,
                        check_output_path=None,
                        changed_files=diff_summary.changed_files,
                        changed_lines=diff_summary.changed_lines,
                        patch_path=str(diff_summary.patch_path),
                        notes_snapshot_path=str(diff_summary.notes_snapshot_path),
                        pause_reason=None,
                        error=final_run.error,
                    )
                )
                self._write_json(round_status_path, round_status_payload)
                break

            if check_result is None or not check_result.passed:
                round_status_payload[round_name] = "failed"
                workflow_status = "failed_recoverable"
                round_results.append(
                    RoundExecutionResult(
                        round_name=round_name,
                        status="failed",
                        codex_run_id=final_run.run_id,
                        codex_success=True,
                        check_passed=False,
                        repaired=repaired,
                        check_output_path=str(final_run.run_dir / "check_result.json")
                        if (final_run.run_dir / "check_result.json").exists()
                        else None,
                        changed_files=diff_summary.changed_files,
                        changed_lines=diff_summary.changed_lines,
                        patch_path=str(diff_summary.patch_path),
                        notes_snapshot_path=str(diff_summary.notes_snapshot_path),
                        pause_reason=None,
                        error=self._check_error_summary(check_result)
                        if check_result is not None
                        else "check result missing",
                    )
                )
                self._write_json(round_status_path, round_status_payload)
                break

            pause_reason = self._evaluate_pause(
                round_name=round_name,
                diff_summary=diff_summary,
                pause_after_round=pause_after_round,
                changed_lines_limit=changed_lines_limit,
                changed_files_limit=changed_files_limit,
            )
            if pause_reason:
                round_status_payload[round_name] = "paused"
                workflow_status = "paused"
            else:
                round_status_payload[round_name] = "completed"

            round_results.append(
                RoundExecutionResult(
                    round_name=round_name,
                    status="paused" if pause_reason else "completed",
                    codex_run_id=final_run.run_id,
                    codex_success=True,
                    check_passed=True,
                    repaired=repaired,
                    check_output_path=str(final_run.run_dir / "check_result.json"),
                    changed_files=diff_summary.changed_files,
                    changed_lines=diff_summary.changed_lines,
                    patch_path=str(diff_summary.patch_path),
                    notes_snapshot_path=str(diff_summary.notes_snapshot_path),
                    pause_reason=pause_reason,
                    error=None,
                )
            )
            self._write_json(round_status_path, round_status_payload)
            if pause_reason:
                break

        finished_at = _now_iso()
        if workflow_status == "succeeded":
            session_payload["status"] = "idle"
        elif workflow_status == "paused":
            session_payload["status"] = "paused"
        else:
            session_payload["status"] = "failed_recoverable"
        session_payload["current_run_id"] = None
        session_payload["updated_at"] = finished_at
        self._write_json(session_path, session_payload)
        self._write_json(round_status_path, round_status_payload)

        result = WorkflowRunResult(
            workflow_run_id=workflow_id,
            status=workflow_status,
            started_at=started_at,
            finished_at=finished_at,
            rounds=round_results,
            workflow_result_path=workflow_dir / "workflow_result.json",
        )
        self._write_json(result.workflow_result_path, result.to_dict())
        return result

    def resume(
        self,
        *,
        project_root: Path | str,
        to_round: RoundName = "final",
        notes_root: Path | str | None = None,
        target_lectures: list[str] | None = None,
        allow_external_refs: bool = False,
        search_enabled: bool = False,
        max_retries: int = 2,
        workflow_run_id: str | None = None,
        auto_repair_check_failures: bool = True,
        pause_after_each_round: bool | None = None,
        max_changed_lines: int | None = None,
        max_changed_files: int | None = None,
    ) -> WorkflowRunResult:
        root = Path(project_root).expanduser().resolve()
        round_status_path = root / "state" / "round_status.json"
        round_status = self._read_json(round_status_path)
        from_round = self._resolve_resume_from_round(round_status=round_status)
        if from_round is None:
            done_id = workflow_run_id or _default_workflow_run_id()
            done_dir = root / "runs" / done_id
            done_dir.mkdir(parents=True, exist_ok=False)
            result = WorkflowRunResult(
                workflow_run_id=done_id,
                status="succeeded",
                started_at=_now_iso(),
                finished_at=_now_iso(),
                rounds=[],
                workflow_result_path=done_dir / "workflow_result.json",
            )
            self._write_json(result.workflow_result_path, result.to_dict())
            return result

        return self.run(
            project_root=root,
            from_round=from_round,
            to_round=to_round,
            notes_root=notes_root,
            target_lectures=target_lectures,
            allow_external_refs=allow_external_refs,
            search_enabled=search_enabled,
            max_retries=max_retries,
            workflow_run_id=workflow_run_id,
            auto_repair_check_failures=auto_repair_check_failures,
            pause_after_each_round=pause_after_each_round,
            max_changed_lines=max_changed_lines,
            max_changed_files=max_changed_files,
        )

    def _select_rounds(self, *, from_round: RoundName, to_round: RoundName) -> list[RoundName]:
        start = RUN_ORDER.index(from_round)
        end = RUN_ORDER.index(to_round)
        if start > end:
            raise ValueError(f"from_round must be <= to_round, got {from_round} -> {to_round}")
        return RUN_ORDER[start : end + 1]

    def _resolve_resume_from_round(self, *, round_status: dict[str, Any]) -> RoundName | None:
        statuses = [str(round_status.get(round_name, "pending")) for round_name in RUN_ORDER]
        first_started_index = 0
        for idx, status in enumerate(statuses):
            if status != "pending":
                first_started_index = idx
                break
        else:
            return "round0"

        for idx in range(first_started_index, len(RUN_ORDER)):
            round_name = RUN_ORDER[idx]
            status = statuses[idx]
            if status in {"pending", "failed", "running"}:
                return round_name
            if status == "paused":
                next_idx = idx + 1
                if next_idx >= len(RUN_ORDER):
                    return None
                return RUN_ORDER[next_idx]
        return None

    def _build_round_prompt(
        self,
        *,
        round_name: RoundName,
        notes_root: Path,
        target_lectures: list[str],
        allow_external_refs: bool,
    ) -> str:
        lecture_scope = ", ".join(target_lectures) if target_lectures else "all lectures"
        external_rule = (
            "Final 轮允许扩展阅读，但必须单独分节并标注来源链接。"
            if allow_external_refs and round_name == "final"
            else "禁止依赖外部资料，仅基于本地素材与现有笔记。"
        )
        round_task = {
            "round1": "按 lecture 生成 skeleton 草稿。",
            "round2": "扩展可读内容、示例、练习与易错点。",
            "round3": "读取 review/feedback.md，仅处理未勾选项并写 resolution。",
            "final": "更新 cheatsheet、清洗 glossary、整理最终一致性。",
        }.get(round_name, "执行当前轮次任务。")
        return (
            "你是课程笔记生成助手。\n"
            f"当前轮次：{round_name}\n"
            f"目标范围：{lecture_scope}\n"
            f"任务：{round_task}\n"
            f"工作目录中的 notes_root: {notes_root}\n"
            f"{external_rule}\n"
            "全局要求：\n"
            "1. 全文中文解释（代码块和专有名词可保留英文）。\n"
            "2. 非平凡结论增加 Source: 标记。\n"
            "3. 只做本轮必要修改，不要大范围重写。\n"
            "4. 完成后结束。\n"
        )

    def _build_repair_prompt(
        self,
        *,
        round_name: RoundName,
        check_result: CheckRunResult,
        notes_root: Path,
    ) -> str:
        payload = check_result.payload or {}
        errors = payload.get("errors", [])
        warnings = payload.get("warnings", [])
        error_text = "\n".join(f"- {item}" for item in errors) if errors else "- 无"
        warning_text = "\n".join(f"- {item}" for item in warnings) if warnings else "- 无"
        return (
            "你是课程笔记修复助手，仅修复检查器指出的问题。\n"
            f"轮次：{round_name}\n"
            f"notes_root: {notes_root}\n"
            "检查错误：\n"
            f"{error_text}\n"
            "检查警告：\n"
            f"{warning_text}\n"
            "要求：\n"
            "1. 只修改与错误直接相关的文件。\n"
            "2. 保持中文解释与 Source 标记规范。\n"
            "3. 不新增无关内容。\n"
            "4. 完成后结束。\n"
        )

    def _check_error_summary(self, check_result: CheckRunResult) -> str:
        payload = check_result.payload or {}
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            return "; ".join(str(item) for item in errors[:3])
        return f"check failed with exit_code={check_result.exit_code}"

    def _evaluate_pause(
        self,
        *,
        round_name: RoundName,
        diff_summary: DiffSummary,
        pause_after_round: bool,
        changed_lines_limit: int,
        changed_files_limit: int,
    ) -> str | None:
        if round_name != "round0":
            if changed_files_limit >= 0 and diff_summary.changed_files > changed_files_limit:
                return (
                    "changed_files threshold exceeded: "
                    f"{diff_summary.changed_files} > {changed_files_limit}"
                )
            if changed_lines_limit >= 0 and diff_summary.changed_lines > changed_lines_limit:
                return (
                    "changed_lines threshold exceeded: "
                    f"{diff_summary.changed_lines} > {changed_lines_limit}"
                )
        if pause_after_round:
            return "pause_after_each_round enabled"
        return None

    def _read_json(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as fp:
            return json.load(fp)

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2, ensure_ascii=False, sort_keys=True)
            fp.write("\n")
        temp_path.replace(path)
