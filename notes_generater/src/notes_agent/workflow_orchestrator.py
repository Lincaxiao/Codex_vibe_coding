from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from .check_runner import CheckRunResult, CheckRunner
from .codex_executor import CodexExecutor, CodexRunRequest, CodexRunResult
from .diff_service import DiffService, DiffSummary
from .lecture_registry_service import LectureRegistryService
from .path_utils import validate_path_component
from .prompt_template_service import PromptTemplateService
from .project_service import ProjectService
from .round0_initializer import Round0Initializer
from .snapshot_service import SnapshotService

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
        snapshot_service: SnapshotService | None = None,
        prompt_template_service: PromptTemplateService | None = None,
        lecture_registry_service: LectureRegistryService | None = None,
    ) -> None:
        self.project_service = project_service or ProjectService()
        self.codex_executor = codex_executor or CodexExecutor()
        self.check_runner = check_runner or CheckRunner()
        self.round0_initializer = round0_initializer or Round0Initializer()
        self.diff_service = diff_service or DiffService()
        self.snapshot_service = snapshot_service or SnapshotService()
        self.prompt_template_service = prompt_template_service or PromptTemplateService()
        self.lecture_registry_service = lecture_registry_service or LectureRegistryService()

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
        progress_callback: Callable[[str], None] | None = None,
    ) -> WorkflowRunResult:
        started_at = _now_iso()
        root = Path(project_root).expanduser().resolve()
        config = self.project_service.load_project_config(root)
        notes = Path(notes_root).expanduser().resolve() if notes_root else config.notes_root
        workflow_id = (
            validate_path_component(workflow_run_id, field_name="workflow_run_id")
            if workflow_run_id is not None
            else _default_workflow_run_id()
        )
        lecture_scope = self.lecture_registry_service.resolve_paths(
            project_root=root,
            target_lectures=target_lectures or [],
        )
        extra_allowed_dirs = self._collect_extra_allowed_dirs(lecture_scope)
        prompt_templates = self.prompt_template_service.load_templates(project_root=root)
        if max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {max_retries}")
        pause_after_round = config.pause_after_each_round if pause_after_each_round is None else pause_after_each_round
        changed_lines_limit = config.max_changed_lines if max_changed_lines is None else max_changed_lines
        changed_files_limit = config.max_changed_files if max_changed_files is None else max_changed_files
        workflow_dir = root / "runs" / workflow_id
        workflow_dir.mkdir(parents=True, exist_ok=False)

        rounds = self._select_rounds(from_round=from_round, to_round=to_round)
        round_results: list[RoundExecutionResult] = []
        workflow_status = "succeeded"
        self._emit_progress(
            progress_callback,
            f"[workflow] 启动 workflow_id={workflow_id}，执行轮次：{from_round}->{to_round} ({', '.join(rounds)})",
        )
        self._emit_progress(
            progress_callback,
            f"[workflow] 目标讲次：{', '.join(lecture_scope.keys())}",
        )

        session_path = root / "state" / "session.json"
        round_status_path = root / "state" / "round_status.json"
        session_payload = self._read_json(session_path)
        round_status_payload = self._read_json(round_status_path)
        session_payload["status"] = "running"
        session_payload["current_run_id"] = workflow_id
        session_payload["updated_at"] = _now_iso()
        self._write_json(session_path, session_payload)

        active_round: RoundName | None = None
        unexpected_error: Exception | None = None
        finished_at = started_at
        try:
            for round_name in rounds:
                active_round = round_name
                round_progress = self._round_progress(progress_callback, round_name=round_name)
                self._emit_progress(progress_callback, f"[workflow] {round_name} 开始")
                round_status_payload[round_name] = "running"
                self._write_json(round_status_path, round_status_payload)
                before_state = self.diff_service.capture_state(notes_root=notes)
                round_artifact_dir = workflow_dir / round_name
                round_artifact_dir.mkdir(parents=True, exist_ok=True)
                self._write_json(
                    round_artifact_dir / "lecture_scope.json",
                    {
                        "lectures": {
                            lec_id: [str(path) for path in paths]
                            for lec_id, paths in lecture_scope.items()
                        }
                    },
                )

                if round_name == "round0":
                    self._emit_progress(round_progress, "初始化笔记骨架")
                    init_result = self.round0_initializer.initialize(
                        project_root=root,
                        notes_root=notes,
                        course_id=config.course_id,
                    )
                    self._write_json(round_artifact_dir / "round0_init_result.json", init_result.to_dict())
                    check_output_path = round_artifact_dir / "check_result.json"
                    self._emit_progress(round_progress, "执行检查")
                    check_result = self.check_runner.run(
                        project_root=root,
                        notes_root=notes,
                        output_path=check_output_path,
                        progress_callback=round_progress,
                    )
                    after_state = self.diff_service.capture_state(notes_root=notes)
                    diff_summary = self.diff_service.write_diff_artifacts(
                        notes_root=notes,
                        before_state=before_state,
                        after_state=after_state,
                        run_dir=round_artifact_dir,
                    )
                    self._emit_progress(
                        round_progress,
                        f"改动统计：files={diff_summary.changed_files}, lines={diff_summary.changed_lines}",
                    )
                    snapshot_error = self._verify_snapshot_integrity_if_present(project_root=root)
                    if snapshot_error:
                        self._emit_progress(round_progress, f"快照校验失败：{snapshot_error}")
                        round_status_payload["round0"] = "failed"
                        workflow_status = "failed_recoverable"
                        round_results.append(
                            RoundExecutionResult(
                                round_name="round0",
                                status="failed",
                                codex_run_id=None,
                                codex_success=None,
                                check_passed=check_result.passed,
                                repaired=False,
                                check_output_path=str(check_output_path),
                                changed_files=diff_summary.changed_files,
                                changed_lines=diff_summary.changed_lines,
                                patch_path=str(diff_summary.patch_path),
                                notes_snapshot_path=str(diff_summary.notes_snapshot_path),
                                pause_reason=None,
                                error=snapshot_error,
                            )
                        )
                        self._write_json(round_status_path, round_status_payload)
                        break
                    if not check_result.passed:
                        self._emit_progress(round_progress, f"检查失败：{self._check_error_summary(check_result)}")
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
                        self._emit_progress(round_progress, f"已暂停：{pause_reason}")
                    else:
                        round_status_payload["round0"] = "completed"
                        self._emit_progress(round_progress, "执行完成")

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
                    lecture_scope=lecture_scope,
                    allow_external_refs=allow_external_refs,
                    template_text=prompt_templates.get(round_name),
                )
                codex_run_id = f"{workflow_id}_{round_name}"
                round_search_enabled = self._resolve_search_enabled(
                    round_name=round_name,
                    search_enabled=search_enabled,
                    allow_external_refs=allow_external_refs,
                )
                self._emit_progress(
                    round_progress,
                    f"调用 Codex：run_id={codex_run_id}, search_enabled={round_search_enabled}",
                )
                codex_result = self.codex_executor.run(
                    CodexRunRequest(
                        project_root=root,
                        notes_root=notes,
                        prompt=prompt,
                        run_id=codex_run_id,
                        search_enabled=round_search_enabled,
                        max_retries=max_retries,
                        extra_allowed_dirs=extra_allowed_dirs,
                    ),
                    progress_callback=round_progress,
                )

                final_run: CodexRunResult = codex_result
                check_result: CheckRunResult | None = None
                repaired = False

                if codex_result.success:
                    self._emit_progress(round_progress, "执行检查")
                    check_result = self.check_runner.run(
                        project_root=root,
                        notes_root=notes,
                        output_path=codex_result.run_dir / "check_result.json",
                        progress_callback=round_progress,
                    )

                    if not check_result.passed and auto_repair_check_failures:
                        self._emit_progress(round_progress, "检查未通过，触发自动修复")
                        repair_prompt = self._build_repair_prompt(
                            round_name=round_name,
                            check_result=check_result,
                            notes_root=notes,
                            template_text=prompt_templates.get("repair"),
                        )
                        repair_run_id = f"{workflow_id}_{round_name}_repair1"
                        repair_result = self.codex_executor.run(
                            CodexRunRequest(
                                project_root=root,
                                notes_root=notes,
                                prompt=repair_prompt,
                                run_id=repair_run_id,
                                search_enabled=round_search_enabled,
                                max_retries=max_retries,
                                extra_allowed_dirs=extra_allowed_dirs,
                            ),
                            progress_callback=round_progress,
                        )
                        repaired = True
                        final_run = repair_result
                        if repair_result.success:
                            self._emit_progress(round_progress, "修复后重新执行检查")
                            check_result = self.check_runner.run(
                                project_root=root,
                                notes_root=notes,
                                output_path=repair_result.run_dir / "check_result.json",
                                progress_callback=round_progress,
                            )
                        else:
                            check_result = None

                after_state = self.diff_service.capture_state(notes_root=notes)
                diff_summary = self.diff_service.write_diff_artifacts(
                    notes_root=notes,
                    before_state=before_state,
                    after_state=after_state,
                    run_dir=round_artifact_dir,
                )
                self._emit_progress(
                    round_progress,
                    f"改动统计：files={diff_summary.changed_files}, lines={diff_summary.changed_lines}",
                )
                snapshot_error = self._verify_snapshot_integrity_if_present(project_root=root)
                if snapshot_error:
                    self._emit_progress(round_progress, f"快照校验失败：{snapshot_error}")
                    check_path = final_run.run_dir / "check_result.json"
                    round_status_payload[round_name] = "failed"
                    workflow_status = "failed_recoverable"
                    round_results.append(
                        RoundExecutionResult(
                            round_name=round_name,
                            status="failed",
                            codex_run_id=final_run.run_id,
                            codex_success=final_run.success,
                            check_passed=check_result.passed if check_result is not None else None,
                            repaired=repaired,
                            check_output_path=str(check_path) if check_path.exists() else None,
                            changed_files=diff_summary.changed_files,
                            changed_lines=diff_summary.changed_lines,
                            patch_path=str(diff_summary.patch_path),
                            notes_snapshot_path=str(diff_summary.notes_snapshot_path),
                            pause_reason=None,
                            error=snapshot_error,
                        )
                    )
                    self._write_json(round_status_path, round_status_payload)
                    break

                if not final_run.success:
                    self._emit_progress(round_progress, f"Codex 执行失败：{final_run.error or 'unknown error'}")
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
                    self._emit_progress(
                        round_progress,
                        f"检查失败：{self._check_error_summary(check_result) if check_result is not None else 'check result missing'}",
                    )
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
                    self._emit_progress(round_progress, f"已暂停：{pause_reason}")
                else:
                    round_status_payload[round_name] = "completed"
                    self._emit_progress(round_progress, "执行完成")

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
        except Exception as exc:
            workflow_status = "failed_recoverable"
            self._emit_progress(progress_callback, f"[workflow] 异常中断：{exc}")
            if active_round is not None and round_status_payload.get(active_round) == "running":
                round_status_payload[active_round] = "failed"
                round_results.append(
                    RoundExecutionResult(
                        round_name=active_round,
                        status="failed",
                        codex_run_id=None,
                        codex_success=None,
                        check_passed=None,
                        repaired=False,
                        check_output_path=None,
                        changed_files=0,
                        changed_lines=0,
                        patch_path=None,
                        notes_snapshot_path=None,
                        pause_reason=None,
                        error=str(exc),
                    )
                )
            unexpected_error = exc
        finally:
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
            self._emit_progress(progress_callback, f"[workflow] 结束，状态：{workflow_status}")

        if unexpected_error is not None:
            raise unexpected_error

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
        progress_callback: Callable[[str], None] | None = None,
    ) -> WorkflowRunResult:
        root = Path(project_root).expanduser().resolve()
        round_status_path = root / "state" / "round_status.json"
        round_status = self._read_json(round_status_path)
        from_round = self._resolve_resume_from_round(round_status=round_status)
        self._emit_progress(progress_callback, f"[workflow] 恢复流程请求，目标轮次：{to_round}")
        if from_round is None:
            session_path = root / "state" / "session.json"
            session_payload = self._read_json(session_path)
            now = _now_iso()
            session_payload["status"] = "idle"
            session_payload["current_run_id"] = None
            session_payload["updated_at"] = now
            self._write_json(session_path, session_payload)
            if str(round_status.get("final", "")) == "paused":
                round_status["final"] = "completed"
                self._write_json(round_status_path, round_status)

            done_id = (
                validate_path_component(workflow_run_id, field_name="workflow_run_id")
                if workflow_run_id is not None
                else _default_workflow_run_id()
            )
            done_dir = root / "runs" / done_id
            done_dir.mkdir(parents=True, exist_ok=False)
            result = WorkflowRunResult(
                workflow_run_id=done_id,
                status="succeeded",
                started_at=now,
                finished_at=now,
                rounds=[],
                workflow_result_path=done_dir / "workflow_result.json",
            )
            self._write_json(result.workflow_result_path, result.to_dict())
            self._emit_progress(progress_callback, "[workflow] 无需恢复，当前已完成全部轮次")
            return result

        if RUN_ORDER.index(from_round) > RUN_ORDER.index(to_round):
            raise ValueError(
                f"无法恢复到 {to_round}: 当前应从 {from_round} 开始，请选择不早于 {from_round} 的目标轮次"
            )
        self._emit_progress(progress_callback, f"[workflow] 将从 {from_round} 恢复到 {to_round}")

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
            progress_callback=progress_callback,
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
        lecture_scope: dict[str, list[Path]],
        allow_external_refs: bool,
        template_text: str | None,
    ) -> str:
        lecture_scope_text = ", ".join(lecture_scope.keys())
        lecture_paths_text = "\n".join(
            f"- {lec_id}: {', '.join(str(path) for path in paths)}"
            for lec_id, paths in lecture_scope.items()
        )
        external_rule = (
            "Final 轮允许扩展阅读，但仍需以本地课程材料为主。"
            if allow_external_refs and round_name == "final"
            else "禁止依赖外部资料，仅基于本地素材与现有笔记。"
        )
        return self._render_prompt_template(
            template_text=template_text,
            values={
                "round_name": round_name,
                "lecture_scope": lecture_scope_text,
                "lecture_paths": lecture_paths_text,
                "notes_root": str(notes_root),
                "external_rule": external_rule,
            },
        )

    def _build_repair_prompt(
        self,
        *,
        round_name: RoundName,
        check_result: CheckRunResult,
        notes_root: Path,
        template_text: str | None,
    ) -> str:
        payload = check_result.payload or {}
        errors = payload.get("errors", [])
        warnings = payload.get("warnings", [])
        error_text = "\n".join(f"- {item}" for item in errors) if errors else "- 无"
        warning_text = "\n".join(f"- {item}" for item in warnings) if warnings else "- 无"
        return self._render_prompt_template(
            template_text=template_text,
            values={
                "round_name": round_name,
                "notes_root": str(notes_root),
                "check_errors": error_text,
                "check_warnings": warning_text,
            },
        )

    def _render_prompt_template(
        self,
        *,
        template_text: str | None,
        values: dict[str, str],
    ) -> str:
        text = template_text or ""
        for key, value in values.items():
            text = text.replace(f"{{{{{key}}}}}", value)
        return text

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

    def _resolve_search_enabled(
        self,
        *,
        round_name: RoundName,
        search_enabled: bool,
        allow_external_refs: bool,
    ) -> bool:
        return search_enabled and allow_external_refs and round_name == "final"

    def _collect_extra_allowed_dirs(self, lecture_scope: dict[str, list[Path]]) -> list[Path]:
        normalized: list[Path] = []
        seen: set[str] = set()
        for paths in lecture_scope.values():
            for path in paths:
                resolved = path if path.is_dir() else path.parent
                key = str(resolved)
                if key in seen:
                    continue
                seen.add(key)
                normalized.append(resolved)
        return normalized

    def _verify_snapshot_integrity_if_present(self, *, project_root: Path) -> str | None:
        source_hashes_path = project_root / "artifacts" / "source_hashes.json"
        if not source_hashes_path.exists():
            return None
        verification = self.snapshot_service.verify_snapshot_hashes(project_root=project_root)
        if verification.valid:
            return None
        if not verification.mismatches:
            return f"snapshot hash verification failed ({verification.snapshot_id})"
        first = verification.mismatches[0]
        return (
            "snapshot hash verification failed: "
            f"{first.get('reason', 'unknown')} @ {first.get('path', '')}"
        )

    def _emit_progress(
        self,
        progress_callback: Callable[[str], None] | None,
        message: str,
    ) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(message)
        except Exception:
            return

    def _round_progress(
        self,
        progress_callback: Callable[[str], None] | None,
        *,
        round_name: RoundName,
    ) -> Callable[[str], None] | None:
        if progress_callback is None:
            return None

        def _emit(message: str) -> None:
            self._emit_progress(progress_callback, f"[{round_name}] {message}")

        return _emit

    def _read_json(self, path: Path) -> dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as fp:
                payload = json.load(fp)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        if isinstance(payload, dict):
            return payload
        return {}

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2, ensure_ascii=False, sort_keys=True)
            fp.write("\n")
        temp_path.replace(path)
