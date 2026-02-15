from __future__ import annotations

import json
import inspect
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

    def preflight(
        self,
        *,
        project_root: Path | str,
        from_round: RoundName = "round1",
        to_round: RoundName = "final",
        notes_root: Path | str | None = None,
        target_lectures: list[str] | None = None,
        allow_external_refs: bool = False,
        search_enabled: bool = False,
        auto_repair_check_failures: bool = True,
        progress_callback: Callable[[str], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        started_at = _now_iso()
        root = Path(project_root).expanduser().resolve()
        checks: list[dict[str, Any]] = []
        errors: list[str] = []
        warnings: list[str] = []
        lecture_scope: dict[str, list[Path]] = {}

        self._emit_progress(progress_callback, "[preflight] 开始执行流程预检查")

        def is_cancelled() -> bool:
            return cancel_check is not None and cancel_check()

        def finalize(
            *,
            context: dict[str, Any],
            cancelled: bool = False,
        ) -> dict[str, Any]:
            return self._finalize_preflight_result(
                started_at=started_at,
                checks=checks,
                errors=errors,
                warnings=warnings,
                context=context,
                progress_callback=progress_callback,
                cancelled=cancelled,
            )

        def add_check(name: str, passed: bool, message: str, *, severity: str = "error") -> None:
            status = "ok" if passed else ("warning" if severity == "warning" else "error")
            checks.append(
                {
                    "name": name,
                    "status": status,
                    "passed": passed,
                    "message": message,
                }
            )
            if not passed:
                entry = f"{name}: {message}"
                if status == "warning":
                    warnings.append(entry)
                else:
                    errors.append(entry)
            label = "通过" if status == "ok" else ("警告" if status == "warning" else "失败")
            self._emit_progress(progress_callback, f"[preflight] {label} {name}: {message}")

        if is_cancelled():
            errors.append("cancelled by user")
            self._emit_progress(progress_callback, "[preflight] 收到取消请求，终止预检查")
            return finalize(context={"project_root": str(root)}, cancelled=True)

        try:
            config = self.project_service.load_project_config(root)
            add_check("project_config", True, str(config.project_root))
        except (ValueError, FileNotFoundError, OSError) as exc:
            add_check("project_config", False, str(exc))
            return finalize(context={"project_root": str(root)})

        if is_cancelled():
            errors.append("cancelled by user")
            self._emit_progress(progress_callback, "[preflight] 收到取消请求，终止预检查")
            return finalize(
                context={
                    "project_root": str(root),
                    "notes_root": str(config.notes_root),
                },
                cancelled=True,
            )

        try:
            rounds = self._select_rounds(from_round=from_round, to_round=to_round)
            add_check("round_range", True, f"{from_round}->{to_round} ({', '.join(rounds)})")
        except ValueError as exc:
            add_check("round_range", False, str(exc))
            return finalize(context={"project_root": str(root)})

        notes = Path(notes_root).expanduser().resolve() if notes_root else config.notes_root
        add_check("notes_root", True, str(notes))

        if is_cancelled():
            errors.append("cancelled by user")
            self._emit_progress(progress_callback, "[preflight] 收到取消请求，终止预检查")
            return finalize(
                context={
                    "project_root": str(root),
                    "notes_root": str(notes),
                    "rounds": rounds,
                },
                cancelled=True,
            )

        templates = self.prompt_template_service.load_templates(project_root=root)
        required_templates = [item for item in rounds if item != "round0"]
        if required_templates and auto_repair_check_failures:
            required_templates.append("repair")
        missing_templates = [item for item in required_templates if not templates.get(item, "").strip()]
        if missing_templates:
            add_check("prompt_templates", False, f"缺少模板: {', '.join(sorted(set(missing_templates)))}")
        else:
            add_check("prompt_templates", True, f"已加载 {len(templates)} 个模板")

        requires_lecture_scope = any(round_name != "round0" for round_name in rounds)
        if requires_lecture_scope:
            if is_cancelled():
                errors.append("cancelled by user")
                self._emit_progress(progress_callback, "[preflight] 收到取消请求，终止预检查")
                return finalize(
                    context={
                        "project_root": str(root),
                        "notes_root": str(notes),
                        "rounds": rounds,
                    },
                    cancelled=True,
                )
            try:
                lecture_scope = self.lecture_registry_service.resolve_paths(
                    project_root=root,
                    target_lectures=target_lectures or [],
                )
                add_check("lecture_scope", True, f"讲次数={len(lecture_scope)}")
            except (ValueError, FileNotFoundError, OSError) as exc:
                add_check("lecture_scope", False, str(exc))

            check_script = notes / "scripts" / "check.sh"
            if check_script.exists() and check_script.is_file():
                add_check("check_script", True, str(check_script))
            else:
                add_check("check_script", False, f"缺少检查脚本: {check_script}（请先执行 round0）")

            if is_cancelled():
                errors.append("cancelled by user")
                self._emit_progress(progress_callback, "[preflight] 收到取消请求，终止预检查")
                return finalize(
                    context={
                        "project_root": str(root),
                        "notes_root": str(notes),
                        "rounds": rounds,
                        "target_lectures": list(lecture_scope.keys()),
                    },
                    cancelled=True,
                )
            probe = self._probe_codex_cli(cancel_check=cancel_check)
            if probe.get("cancelled") is True:
                errors.append("cancelled by user")
                self._emit_progress(progress_callback, "[preflight] Codex CLI 探测已取消")
                return finalize(
                    context={
                        "project_root": str(root),
                        "notes_root": str(notes),
                        "rounds": rounds,
                        "target_lectures": list(lecture_scope.keys()),
                    },
                    cancelled=True,
                )
            if probe["available"] is True:
                add_check("codex_cli", True, f"version={probe['version']}")
            elif probe["available"] is False:
                add_check("codex_cli", False, probe["error"] or "codex CLI 不可用")
            else:
                add_check("codex_cli", False, probe["error"] or "codex CLI 预检查已跳过", severity="warning")
        else:
            add_check("lecture_scope", True, "仅执行 round0，无需讲次映射")

        writable_root_ok, writable_root_message = self._ensure_writable_dir(root)
        add_check("project_root_writable", writable_root_ok, writable_root_message)

        writable_notes_ok, writable_notes_message = self._ensure_writable_dir(notes, prefer_parent_if_missing=True)
        add_check("notes_root_writable", writable_notes_ok, writable_notes_message)

        effective_search_rounds = [
            round_name
            for round_name in rounds
            if self._resolve_search_enabled(
                round_name=round_name,
                search_enabled=search_enabled,
                allow_external_refs=allow_external_refs,
            )
        ]
        if effective_search_rounds:
            add_check("search_policy", True, f"启用网页搜索轮次: {', '.join(effective_search_rounds)}")
        elif search_enabled and not allow_external_refs:
            add_check(
                "search_policy",
                False,
                "已请求搜索，但未允许外部参考；实际不会启用网页搜索",
                severity="warning",
            )
        else:
            add_check("search_policy", True, "网页搜索未启用")

        context = {
            "project_root": str(root),
            "notes_root": str(notes),
            "rounds": rounds,
            "target_lectures": list(lecture_scope.keys()),
            "lecture_scope": {
                lec_id: [str(path) for path in paths]
                for lec_id, paths in lecture_scope.items()
            },
            "effective_search_rounds": effective_search_rounds,
            "allow_external_refs": allow_external_refs,
            "search_enabled": search_enabled,
        }
        return finalize(context=context)

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
        cancel_check: Callable[[], bool] | None = None,
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
        rounds = self._select_rounds(from_round=from_round, to_round=to_round)
        requires_lecture_scope = any(round_name != "round0" for round_name in rounds)
        if requires_lecture_scope:
            lecture_scope = self.lecture_registry_service.resolve_paths(
                project_root=root,
                target_lectures=target_lectures or [],
            )
            extra_allowed_dirs = self._collect_extra_allowed_dirs(lecture_scope)
        else:
            lecture_scope = {}
            extra_allowed_dirs = []
        prompt_templates = self.prompt_template_service.load_templates(project_root=root)
        if max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {max_retries}")
        pause_after_round = config.pause_after_each_round if pause_after_each_round is None else pause_after_each_round
        changed_lines_limit = config.max_changed_lines if max_changed_lines is None else max_changed_lines
        changed_files_limit = config.max_changed_files if max_changed_files is None else max_changed_files
        workflow_dir = root / "runs" / workflow_id
        workflow_dir.mkdir(parents=True, exist_ok=False)
        round_results: list[RoundExecutionResult] = []
        workflow_status = "succeeded"
        self._emit_progress(
            progress_callback,
            f"[workflow] 启动 workflow_id={workflow_id}，执行轮次：{from_round}->{to_round} ({', '.join(rounds)})",
        )
        if lecture_scope:
            self._emit_progress(
                progress_callback,
                f"[workflow] 目标讲次：{', '.join(lecture_scope.keys())}",
            )
        else:
            self._emit_progress(progress_callback, "[workflow] 当前执行范围仅 round0，跳过讲次映射检查")

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
                if cancel_check is not None and cancel_check():
                    workflow_status = "paused"
                    self._emit_progress(progress_callback, "[workflow] 收到取消请求，流程已暂停")
                    break
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
                    check_result = self._run_check(
                        project_root=root,
                        notes_root=notes,
                        output_path=check_output_path,
                        progress_callback=round_progress,
                        cancel_check=cancel_check,
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
                        if check_result.exit_code == 130:
                            round_status_payload["round0"] = "paused"
                            workflow_status = "paused"
                            round_results.append(
                                RoundExecutionResult(
                                    round_name="round0",
                                    status="paused",
                                    codex_run_id=None,
                                    codex_success=None,
                                    check_passed=False,
                                    repaired=False,
                                    check_output_path=str(check_output_path),
                                    changed_files=diff_summary.changed_files,
                                    changed_lines=diff_summary.changed_lines,
                                    patch_path=str(diff_summary.patch_path),
                                    notes_snapshot_path=str(diff_summary.notes_snapshot_path),
                                    pause_reason="cancelled by user",
                                    error="cancelled by user",
                                )
                            )
                            self._write_json(round_status_path, round_status_payload)
                            break
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
                codex_result = self._run_codex(
                    request=CodexRunRequest(
                        project_root=root,
                        notes_root=notes,
                        prompt=prompt,
                        run_id=codex_run_id,
                        search_enabled=round_search_enabled,
                        max_retries=max_retries,
                        extra_allowed_dirs=extra_allowed_dirs,
                    ),
                    progress_callback=round_progress,
                    cancel_check=cancel_check,
                )

                final_run: CodexRunResult = codex_result
                check_result: CheckRunResult | None = None
                repaired = False

                if codex_result.success:
                    self._emit_progress(round_progress, "执行检查")
                    check_result = self._run_check(
                        project_root=root,
                        notes_root=notes,
                        output_path=codex_result.run_dir / "check_result.json",
                        progress_callback=round_progress,
                        cancel_check=cancel_check,
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
                        repair_result = self._run_codex(
                            request=CodexRunRequest(
                                project_root=root,
                                notes_root=notes,
                                prompt=repair_prompt,
                                run_id=repair_run_id,
                                search_enabled=round_search_enabled,
                                max_retries=max_retries,
                                extra_allowed_dirs=extra_allowed_dirs,
                            ),
                            progress_callback=round_progress,
                            cancel_check=cancel_check,
                        )
                        repaired = True
                        final_run = repair_result
                        if repair_result.success:
                            self._emit_progress(round_progress, "修复后重新执行检查")
                            check_result = self._run_check(
                                project_root=root,
                                notes_root=notes,
                                output_path=repair_result.run_dir / "check_result.json",
                                progress_callback=round_progress,
                                cancel_check=cancel_check,
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
                    if final_run.exit_code == 130:
                        round_status_payload[round_name] = "paused"
                        workflow_status = "paused"
                        round_results.append(
                            RoundExecutionResult(
                                round_name=round_name,
                                status="paused",
                                codex_run_id=final_run.run_id,
                                codex_success=False,
                                check_passed=None,
                                repaired=repaired,
                                check_output_path=None,
                                changed_files=diff_summary.changed_files,
                                changed_lines=diff_summary.changed_lines,
                                patch_path=str(diff_summary.patch_path),
                                notes_snapshot_path=str(diff_summary.notes_snapshot_path),
                                pause_reason="cancelled by user",
                                error="cancelled by user",
                            )
                        )
                        self._write_json(round_status_path, round_status_payload)
                        self._emit_progress(round_progress, "收到取消请求，轮次已暂停")
                        break
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
                    if check_result is not None and check_result.exit_code == 130:
                        round_status_payload[round_name] = "paused"
                        workflow_status = "paused"
                        round_results.append(
                            RoundExecutionResult(
                                round_name=round_name,
                                status="paused",
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
                                pause_reason="cancelled by user",
                                error="cancelled by user",
                            )
                        )
                        self._write_json(round_status_path, round_status_payload)
                        self._emit_progress(round_progress, "检查阶段已取消，轮次暂停")
                        break
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
        cancel_check: Callable[[], bool] | None = None,
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
            cancel_check=cancel_check,
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

    def _run_codex(
        self,
        *,
        request: CodexRunRequest,
        progress_callback: Callable[[str], None] | None,
        cancel_check: Callable[[], bool] | None,
    ) -> CodexRunResult:
        run_callable = self.codex_executor.run
        kwargs: dict[str, Any] = {
            "progress_callback": progress_callback,
        }
        if cancel_check is not None and self._callable_supports_kwarg(run_callable, "cancel_check"):
            kwargs["cancel_check"] = cancel_check
        return run_callable(request, **kwargs)

    def _run_check(
        self,
        *,
        project_root: Path,
        notes_root: Path,
        output_path: Path,
        progress_callback: Callable[[str], None] | None,
        cancel_check: Callable[[], bool] | None,
    ) -> CheckRunResult:
        run_callable = self.check_runner.run
        kwargs: dict[str, Any] = {
            "project_root": project_root,
            "notes_root": notes_root,
            "output_path": output_path,
            "progress_callback": progress_callback,
        }
        if cancel_check is not None and self._callable_supports_kwarg(run_callable, "cancel_check"):
            kwargs["cancel_check"] = cancel_check
        return run_callable(**kwargs)

    def _callable_supports_kwarg(self, target: Callable[..., Any], name: str) -> bool:
        try:
            signature = inspect.signature(target)
        except (TypeError, ValueError):
            return False
        parameter = signature.parameters.get(name)
        if parameter is None:
            return False
        return parameter.kind in {
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }

    def _probe_codex_cli(
        self,
        *,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        probe = getattr(self.codex_executor, "probe_cli", None)
        if probe is None or not callable(probe):
            return {
                "available": None,
                "version": "unknown",
                "error": "当前执行器未实现 codex CLI 预检查接口",
                "cancelled": False,
            }
        try:
            if cancel_check is not None and self._callable_supports_kwarg(probe, "cancel_check"):
                payload = probe(cancel_check=cancel_check)
            else:
                payload = probe()
        except Exception as exc:
            return {
                "available": False,
                "version": "unknown",
                "error": f"codex CLI 预检查失败: {exc}",
                "cancelled": False,
            }
        available = payload.get("available")
        version = str(payload.get("version", "unknown"))
        error = payload.get("error")
        cancelled = bool(payload.get("cancelled", False))
        return {
            "available": available if isinstance(available, bool) else None,
            "version": version,
            "error": str(error) if error is not None else None,
            "cancelled": cancelled,
        }

    def _ensure_writable_dir(
        self,
        path: Path,
        *,
        prefer_parent_if_missing: bool = False,
    ) -> tuple[bool, str]:
        if path.exists() and not path.is_dir():
            return (False, f"不是目录: {path}")
        target = path
        if not path.exists():
            if prefer_parent_if_missing:
                target = path.parent
            else:
                return (False, f"目录不存在: {path}")
        if not target.exists():
            return (False, f"目录不存在: {target}")
        if not target.is_dir():
            return (False, f"不是目录: {target}")
        probe_file = target / f".notes_agent_write_probe_{uuid.uuid4().hex}"
        try:
            probe_file.write_text("probe\n", encoding="utf-8")
            probe_file.unlink()
        except OSError as exc:
            return (False, f"目录不可写: {target} ({exc})")
        return (True, f"目录可写: {target}")

    def _finalize_preflight_result(
        self,
        *,
        started_at: str,
        checks: list[dict[str, Any]],
        errors: list[str],
        warnings: list[str],
        context: dict[str, Any],
        progress_callback: Callable[[str], None] | None,
        cancelled: bool = False,
    ) -> dict[str, Any]:
        finished_at = _now_iso()
        passed = len(errors) == 0 and not cancelled
        payload = {
            "passed": passed,
            "cancelled": cancelled,
            "errors": errors,
            "warnings": warnings,
            "checks": checks,
            "context": context,
            "started_at": started_at,
            "finished_at": finished_at,
        }
        self._emit_progress(progress_callback, f"[preflight] 结束 passed={passed}, cancelled={cancelled}")
        return payload

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
