from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

from notes_agent.check_runner import CheckRunResult, CheckRunner
from notes_agent.codex_executor import CodexRunRequest, CodexRunResult
from notes_agent.lecture_registry_service import LectureRegistryService
from notes_agent.models import CreateProjectRequest
from notes_agent.project_service import ProjectService
from notes_agent.run_history_service import RunHistoryService
from notes_agent.round0_initializer import Round0Initializer
from notes_agent.workflow_orchestrator import WorkflowOrchestrator


class FakeCodexExecutor:
    def __init__(
        self,
        success_by_run_id: dict[str, bool] | None = None,
        default_success: bool = True,
        mutate_rel_path: str | None = None,
    ) -> None:
        self.success_by_run_id = success_by_run_id or {}
        self.default_success = default_success
        self.mutate_rel_path = mutate_rel_path
        self.calls: list[CodexRunRequest] = []

    def run(
        self,
        request: CodexRunRequest,
        *,
        progress_callback: Callable[[str], None] | None = None,
    ) -> CodexRunResult:
        self.calls.append(request)
        run_id = request.run_id or "missing-run-id"
        run_dir = request.project_root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        prompt_path = run_dir / "prompt.md"
        stdout_log_path = run_dir / "codex_stdout.log"
        last_message_path = run_dir / "codex_last_message.md"
        run_manifest_path = run_dir / "run_manifest.json"

        prompt_path.write_text(request.prompt, encoding="utf-8")
        stdout_log_path.write_text("fake codex output\n", encoding="utf-8")
        last_message_path.write_text("fake last message\n", encoding="utf-8")
        run_manifest_path.write_text("{}", encoding="utf-8")

        success = self.success_by_run_id.get(run_id, self.default_success)
        if success and self.mutate_rel_path:
            target = request.notes_root / self.mutate_rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            existing = target.read_text(encoding="utf-8") if target.exists() else ""
            target.write_text(existing + f"变更-{run_id}\n", encoding="utf-8")
        return CodexRunResult(
            run_id=run_id,
            run_dir=run_dir,
            success=success,
            attempts=1,
            exit_code=0 if success else 1,
            prompt_path=prompt_path,
            stdout_log_path=stdout_log_path,
            last_message_path=last_message_path,
            run_manifest_path=run_manifest_path,
            error=None if success else "forced failure",
        )


class FakeCodexExecutorWithProbe(FakeCodexExecutor):
    def __init__(
        self,
        *,
        available: bool = True,
        version: str = "codex-cli 0.100.0",
        error: str | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._probe_payload = {
            "available": available,
            "version": version,
            "error": error,
        }

    def probe_cli(self, *, cancel_check: Callable[[], bool] | None = None) -> dict[str, object]:
        if cancel_check is not None and cancel_check():
            return {
                "available": False,
                "version": "unknown (cancelled)",
                "error": "cancelled by user",
                "cancelled": True,
            }
        payload = dict(self._probe_payload)
        payload.setdefault("cancelled", False)
        return payload


class RaisingCodexExecutor:
    def run(
        self,
        request: CodexRunRequest,
        *,
        progress_callback: Callable[[str], None] | None = None,
    ) -> CodexRunResult:
        raise RuntimeError("boom during codex execution")


class FakeCheckRunner:
    def __init__(self, outcomes: list[bool] | None = None) -> None:
        self.outcomes = outcomes or [True]
        self.calls = 0

    def run(
        self,
        *,
        project_root: Path | str,
        notes_root: Path | str,
        output_path: Path | str | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> CheckRunResult:
        index = min(self.calls, len(self.outcomes) - 1)
        passed = self.outcomes[index]
        self.calls += 1
        payload = {
            "passed": passed,
            "errors": [] if passed else ["mock check failed"],
            "warnings": [],
        }
        result = CheckRunResult(
            passed=passed,
            exit_code=0 if passed else 1,
            stdout=json.dumps(payload),
            stderr="",
            payload=payload,
            started_at="2026-01-01T00:00:00+00:00",
            finished_at="2026-01-01T00:00:01+00:00",
            check_script_path=Path(notes_root) / "scripts" / "check.sh",
        )
        if output_path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result.to_dict(), ensure_ascii=False), encoding="utf-8")
        return result


class WorkflowOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = TemporaryDirectory()
        self.tmp_path = Path(self._tmp_dir.name)
        self.project_service = ProjectService()
        self.course_root = self.tmp_path / "course"
        self.config = self.project_service.create_project(
            CreateProjectRequest(course_id="workflow-test", course_root=self.course_root)
        )
        self.lecture_source_dir = self.course_root / "materials" / "LEC01"
        self.lecture_source_dir.mkdir(parents=True, exist_ok=True)
        (self.lecture_source_dir / "slides.md").write_text("lec01 slides\n", encoding="utf-8")
        self.lecture_registry_service = LectureRegistryService()
        self.lecture_registry_service.upsert_lecture(
            project_root=self.config.project_root,
            lec_id="LEC01",
            paths=[self.lecture_source_dir],
        )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_successful_workflow_rounds(self) -> None:
        fake_executor = FakeCodexExecutor(default_success=True, mutate_rel_path="notes/lectures/lecture01.md")
        fake_check = FakeCheckRunner(outcomes=[True, True])
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=fake_executor,  # type: ignore[arg-type]
            check_runner=fake_check,  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )

        result = orchestrator.run(
            project_root=self.config.project_root,
            from_round="round1",
            to_round="round2",
            workflow_run_id="wf_success",
        )

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(result.rounds), 2)
        self.assertEqual(result.rounds[0].status, "completed")
        self.assertEqual(result.rounds[1].status, "completed")
        self.assertTrue(result.workflow_result_path.exists())

        round_status = json.loads((self.config.project_root / "state" / "round_status.json").read_text(encoding="utf-8"))
        self.assertEqual(round_status["round1"], "completed")
        self.assertEqual(round_status["round2"], "completed")
        history = RunHistoryService()
        patch = history.read_patch(project_root=self.config.project_root, run_id="wf_success", round_name="round2")
        self.assertIsNotNone(patch)
        assert patch is not None
        self.assertIn("--- a/", patch)
        latest_patch = history.read_patch(project_root=self.config.project_root, run_id="wf_success")
        self.assertIsNotNone(latest_patch)

    def test_codex_failure_stops_workflow(self) -> None:
        fake_executor = FakeCodexExecutor(success_by_run_id={"wf_fail_round1_round1": False}, default_success=True)
        fake_check = FakeCheckRunner(outcomes=[True])
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=fake_executor,  # type: ignore[arg-type]
            check_runner=fake_check,  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )

        result = orchestrator.run(
            project_root=self.config.project_root,
            from_round="round1",
            to_round="round3",
            workflow_run_id="wf_fail_round1",
        )

        self.assertEqual(result.status, "failed_recoverable")
        self.assertEqual(len(result.rounds), 1)
        self.assertEqual(result.rounds[0].round_name, "round1")
        self.assertEqual(result.rounds[0].status, "failed")

    def test_check_failure_triggers_single_repair(self) -> None:
        fake_executor = FakeCodexExecutor(default_success=True)
        fake_check = FakeCheckRunner(outcomes=[False, True])
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=fake_executor,  # type: ignore[arg-type]
            check_runner=fake_check,  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )

        result = orchestrator.run(
            project_root=self.config.project_root,
            from_round="round1",
            to_round="round1",
            workflow_run_id="wf_repair",
        )

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(result.rounds), 1)
        self.assertTrue(result.rounds[0].repaired)
        self.assertEqual(result.rounds[0].codex_run_id, "wf_repair_round1_repair1")
        self.assertEqual(len(fake_executor.calls), 2)
        self.assertTrue(result.rounds[0].changed_files >= 0)

    def test_pause_when_changed_lines_exceed_threshold(self) -> None:
        fake_executor = FakeCodexExecutor(default_success=True, mutate_rel_path="notes/lectures/lecture01.md")
        fake_check = FakeCheckRunner(outcomes=[True])
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=fake_executor,  # type: ignore[arg-type]
            check_runner=fake_check,  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )

        result = orchestrator.run(
            project_root=self.config.project_root,
            from_round="round1",
            to_round="round1",
            workflow_run_id="wf_pause_threshold",
            max_changed_lines=0,
        )

        self.assertEqual(result.status, "paused")
        self.assertEqual(len(result.rounds), 1)
        self.assertEqual(result.rounds[0].status, "paused")
        self.assertIsNotNone(result.rounds[0].pause_reason)

    def test_pause_after_each_round(self) -> None:
        fake_executor = FakeCodexExecutor(default_success=True)
        fake_check = FakeCheckRunner(outcomes=[True])
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=fake_executor,  # type: ignore[arg-type]
            check_runner=fake_check,  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )

        result = orchestrator.run(
            project_root=self.config.project_root,
            from_round="round1",
            to_round="round3",
            workflow_run_id="wf_pause_each",
            pause_after_each_round=True,
        )

        self.assertEqual(result.status, "paused")
        self.assertEqual(len(result.rounds), 1)
        self.assertEqual(result.rounds[0].round_name, "round1")
        self.assertEqual(result.rounds[0].status, "paused")

    def test_round0_only_workflow(self) -> None:
        fake_executor = FakeCodexExecutor(default_success=True)
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=fake_executor,  # type: ignore[arg-type]
            check_runner=CheckRunner(),
            round0_initializer=Round0Initializer(),
        )

        result = orchestrator.run(
            project_root=self.config.project_root,
            from_round="round0",
            to_round="round0",
            workflow_run_id="wf_round0",
        )

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(result.rounds), 1)
        self.assertEqual(result.rounds[0].round_name, "round0")
        self.assertTrue((self.config.notes_root / "scripts" / "check.sh").exists())

    def test_round0_only_workflow_does_not_require_lecture_registry(self) -> None:
        self.lecture_registry_service.remove_lecture(
            project_root=self.config.project_root,
            lec_id="LEC01",
        )
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=FakeCodexExecutor(default_success=True),  # type: ignore[arg-type]
            check_runner=CheckRunner(),
            round0_initializer=Round0Initializer(),
        )

        result = orchestrator.run(
            project_root=self.config.project_root,
            from_round="round0",
            to_round="round0",
            workflow_run_id="wf_round0_no_registry",
        )

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(result.rounds), 1)
        self.assertEqual(result.rounds[0].round_name, "round0")

    def test_resume_from_paused_round(self) -> None:
        fake_executor = FakeCodexExecutor(default_success=True, mutate_rel_path="notes/lectures/lecture01.md")
        fake_check = FakeCheckRunner(outcomes=[True, True])
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=fake_executor,  # type: ignore[arg-type]
            check_runner=fake_check,  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )

        first = orchestrator.run(
            project_root=self.config.project_root,
            from_round="round1",
            to_round="round3",
            workflow_run_id="wf_pause_for_resume",
            pause_after_each_round=True,
        )
        self.assertEqual(first.status, "paused")
        self.assertEqual(first.rounds[0].round_name, "round1")

        resumed = orchestrator.resume(
            project_root=self.config.project_root,
            to_round="round3",
            workflow_run_id="wf_resumed",
            pause_after_each_round=False,
        )
        self.assertIn(resumed.status, {"succeeded", "paused"})
        if resumed.rounds:
            self.assertEqual(resumed.rounds[0].round_name, "round2")

    def test_resume_when_all_rounds_completed_returns_noop(self) -> None:
        round_status_path = self.config.project_root / "state" / "round_status.json"
        round_status_path.write_text(
            json.dumps(
                {
                    "round0": "completed",
                    "round1": "completed",
                    "round2": "completed",
                    "round3": "completed",
                    "final": "completed",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        session_path = self.config.project_root / "state" / "session.json"
        session_path.write_text(
            json.dumps(
                {
                    "course_id": self.config.course_id,
                    "status": "paused",
                    "current_run_id": "wf_old",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-02T00:00:00+00:00",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=FakeCodexExecutor(default_success=True),  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )
        result = orchestrator.resume(
            project_root=self.config.project_root,
            workflow_run_id="wf_resume_noop",
        )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.rounds, [])
        session = json.loads(session_path.read_text(encoding="utf-8"))
        self.assertEqual(session["status"], "idle")
        self.assertIsNone(session["current_run_id"])

    def test_unexpected_exception_converges_running_state(self) -> None:
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=RaisingCodexExecutor(),  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )

        with self.assertRaisesRegex(RuntimeError, "boom during codex execution"):
            orchestrator.run(
                project_root=self.config.project_root,
                from_round="round1",
                to_round="round1",
                workflow_run_id="wf_boom",
            )

        session = json.loads((self.config.project_root / "state" / "session.json").read_text(encoding="utf-8"))
        round_status = json.loads((self.config.project_root / "state" / "round_status.json").read_text(encoding="utf-8"))
        self.assertEqual(session["status"], "failed_recoverable")
        self.assertIsNone(session["current_run_id"])
        self.assertEqual(round_status["round1"], "failed")

    def test_resume_rejects_target_round_earlier_than_resume_point(self) -> None:
        round_status_path = self.config.project_root / "state" / "round_status.json"
        round_status_path.write_text(
            json.dumps(
                {
                    "round0": "completed",
                    "round1": "completed",
                    "round2": "failed",
                    "round3": "pending",
                    "final": "pending",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=FakeCodexExecutor(default_success=True),  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )

        with self.assertRaisesRegex(ValueError, "不早于 round2"):
            orchestrator.resume(
                project_root=self.config.project_root,
                to_round="round1",
                workflow_run_id="wf_resume_invalid_target",
            )

    def test_workflow_run_id_path_traversal_rejected(self) -> None:
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=FakeCodexExecutor(default_success=True),  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )

        with self.assertRaisesRegex(ValueError, "workflow_run_id must be a single path component"):
            orchestrator.run(
                project_root=self.config.project_root,
                from_round="round1",
                to_round="round1",
                workflow_run_id="../wf_escape",
            )

    def test_resume_when_final_paused_converges_without_rerun(self) -> None:
        round_status_path = self.config.project_root / "state" / "round_status.json"
        round_status_path.write_text(
            json.dumps(
                {
                    "round0": "completed",
                    "round1": "completed",
                    "round2": "completed",
                    "round3": "completed",
                    "final": "paused",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=FakeCodexExecutor(default_success=True),  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )

        result = orchestrator.resume(
            project_root=self.config.project_root,
            to_round="final",
            workflow_run_id="wf_resume_final_paused",
        )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.rounds, [])
        round_status = json.loads(round_status_path.read_text(encoding="utf-8"))
        self.assertEqual(round_status["final"], "completed")

    def test_run_tolerates_corrupted_state_json(self) -> None:
        (self.config.project_root / "state" / "session.json").write_text("{broken\n", encoding="utf-8")
        (self.config.project_root / "state" / "round_status.json").write_text("{broken\n", encoding="utf-8")

        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=FakeCodexExecutor(default_success=True),  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )
        result = orchestrator.run(
            project_root=self.config.project_root,
            from_round="round1",
            to_round="round1",
            workflow_run_id="wf_corrupt_state",
        )
        self.assertEqual(result.status, "succeeded")

    def test_run_fails_when_snapshot_hashes_invalid(self) -> None:
        source_hashes_path = self.config.project_root / "artifacts" / "source_hashes.json"
        source_hashes_path.parent.mkdir(parents=True, exist_ok=True)
        source_hashes_path.write_text(
            json.dumps(
                {
                    "snapshot_id": "snap-invalid",
                    "files": {"../escape.txt": "deadbeef"},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=FakeCodexExecutor(default_success=True),  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )
        result = orchestrator.run(
            project_root=self.config.project_root,
            from_round="round1",
            to_round="round1",
            workflow_run_id="wf_snapshot_invalid",
        )
        self.assertEqual(result.status, "failed_recoverable")
        self.assertEqual(result.rounds[0].status, "failed")
        self.assertIn("snapshot hash verification failed", result.rounds[0].error or "")

    def test_non_final_round_forces_search_disabled(self) -> None:
        fake_executor = FakeCodexExecutor(default_success=True)
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=fake_executor,  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )
        orchestrator.run(
            project_root=self.config.project_root,
            from_round="round1",
            to_round="round1",
            workflow_run_id="wf_search_round1",
            search_enabled=True,
            allow_external_refs=True,
        )
        self.assertFalse(fake_executor.calls[0].search_enabled)

    def test_final_round_allows_search_when_external_refs_enabled(self) -> None:
        fake_executor = FakeCodexExecutor(default_success=True)
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=fake_executor,  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )
        orchestrator.run(
            project_root=self.config.project_root,
            from_round="final",
            to_round="final",
            workflow_run_id="wf_search_final",
            search_enabled=True,
            allow_external_refs=True,
        )
        self.assertTrue(fake_executor.calls[0].search_enabled)

    def test_workflow_emits_progress_messages(self) -> None:
        fake_executor = FakeCodexExecutor(default_success=True)
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=fake_executor,  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )
        messages: list[str] = []

        result = orchestrator.run(
            project_root=self.config.project_root,
            from_round="round1",
            to_round="round1",
            workflow_run_id="wf_progress",
            progress_callback=messages.append,
        )

        self.assertEqual(result.status, "succeeded")
        self.assertTrue(any("[workflow] 启动 workflow_id=wf_progress" in item for item in messages))
        self.assertTrue(any("[workflow] round1 开始" in item for item in messages))
        self.assertTrue(any("[round1] 调用 Codex" in item for item in messages))
        self.assertTrue(any("[workflow] 结束，状态：succeeded" in item for item in messages))

    def test_default_prompt_is_self_contained_without_source_requirement(self) -> None:
        fake_executor = FakeCodexExecutor(default_success=True)
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=fake_executor,  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )
        orchestrator.run(
            project_root=self.config.project_root,
            from_round="round1",
            to_round="round1",
            workflow_run_id="wf_self_contained_prompt",
        )
        prompt = fake_executor.calls[0].prompt
        self.assertIn("必须自包含", prompt)
        self.assertNotIn("Source:", prompt)

    def test_custom_prompt_templates_are_applied(self) -> None:
        fake_executor = FakeCodexExecutor(default_success=True)
        fake_check = FakeCheckRunner(outcomes=[False, True])
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=fake_executor,  # type: ignore[arg-type]
            check_runner=fake_check,  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )
        custom_templates = {
            "round1": "ROUND1 CUSTOM {{lecture_scope}} {{lecture_paths}}",
            "repair": "REPAIR CUSTOM {{check_errors}} {{check_warnings}}",
        }
        template_path = self.config.project_root / "artifacts" / "prompt_templates.json"
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_text(json.dumps(custom_templates, ensure_ascii=False) + "\n", encoding="utf-8")

        result = orchestrator.run(
            project_root=self.config.project_root,
            from_round="round1",
            to_round="round1",
            workflow_run_id="wf_custom_prompt",
            target_lectures=["LEC01"],
        )

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(fake_executor.calls), 2)
        self.assertIn("ROUND1 CUSTOM LEC01", fake_executor.calls[0].prompt)
        self.assertIn(str(self.lecture_source_dir), fake_executor.calls[0].prompt)
        self.assertIn("REPAIR CUSTOM", fake_executor.calls[1].prompt)
        self.assertIn("mock check failed", fake_executor.calls[1].prompt)

    def test_target_lecture_scope_propagates_to_prompt_and_codex_access(self) -> None:
        fake_executor = FakeCodexExecutor(default_success=True)
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=fake_executor,  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )

        result = orchestrator.run(
            project_root=self.config.project_root,
            from_round="round1",
            to_round="round1",
            workflow_run_id="wf_target_dir",
            target_lectures=["LEC01"],
        )

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(fake_executor.calls), 1)
        request = fake_executor.calls[0]
        self.assertIn(str(self.lecture_source_dir), request.prompt)
        self.assertEqual(
            [path.resolve() for path in (request.extra_allowed_dirs or [])],
            [self.lecture_source_dir.resolve()],
        )

    def test_workflow_without_target_uses_all_registered_lectures(self) -> None:
        extra_dir = self.course_root / "materials" / "LEC02"
        extra_dir.mkdir(parents=True, exist_ok=True)
        (extra_dir / "notes.txt").write_text("lec02\n", encoding="utf-8")
        self.lecture_registry_service.upsert_lecture(
            project_root=self.config.project_root,
            lec_id="LEC02",
            paths=[extra_dir],
        )

        fake_executor = FakeCodexExecutor(default_success=True)
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=fake_executor,  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )
        result = orchestrator.run(
            project_root=self.config.project_root,
            from_round="round1",
            to_round="round1",
            workflow_run_id="wf_all_lectures",
        )

        self.assertEqual(result.status, "succeeded")
        prompt = fake_executor.calls[0].prompt
        self.assertIn("LEC01", prompt)
        self.assertIn("LEC02", prompt)
        self.assertIn(str(self.lecture_source_dir), prompt)
        self.assertIn(str(extra_dir), prompt)

    def test_unknown_target_lecture_rejected(self) -> None:
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=FakeCodexExecutor(default_success=True),  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )

        with self.assertRaisesRegex(ValueError, "目标讲次未注册"):
            orchestrator.run(
                project_root=self.config.project_root,
                from_round="round1",
                to_round="round1",
                workflow_run_id="wf_target_dir_missing",
                target_lectures=["LEC404"],
            )

    def test_workflow_rejects_when_lecture_registry_empty(self) -> None:
        self.lecture_registry_service.remove_lecture(
            project_root=self.config.project_root,
            lec_id="LEC01",
        )
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=FakeCodexExecutor(default_success=True),  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )
        with self.assertRaisesRegex(ValueError, "未配置可用讲次"):
            orchestrator.run(
                project_root=self.config.project_root,
                from_round="round1",
                to_round="round1",
                workflow_run_id="wf_missing_registry",
            )

    def test_workflow_can_be_cancelled_before_round_start(self) -> None:
        fake_executor = FakeCodexExecutor(default_success=True)
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=fake_executor,  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )
        result = orchestrator.run(
            project_root=self.config.project_root,
            from_round="round1",
            to_round="round1",
            workflow_run_id="wf_cancelled_before_start",
            cancel_check=lambda: True,
        )
        self.assertEqual(result.status, "paused")
        self.assertEqual(result.rounds, [])
        round_status = json.loads((self.config.project_root / "state" / "round_status.json").read_text(encoding="utf-8"))
        self.assertEqual(round_status["round1"], "pending")

    def test_preflight_round0_only_passes_without_lecture_registry(self) -> None:
        self.lecture_registry_service.remove_lecture(
            project_root=self.config.project_root,
            lec_id="LEC01",
        )
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=FakeCodexExecutor(default_success=True),  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )
        payload = orchestrator.preflight(
            project_root=self.config.project_root,
            from_round="round0",
            to_round="round0",
        )
        self.assertTrue(payload["passed"])
        self.assertEqual(payload["errors"], [])

    def test_preflight_round1_fails_when_check_script_missing(self) -> None:
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=FakeCodexExecutor(default_success=True),  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )
        payload = orchestrator.preflight(
            project_root=self.config.project_root,
            from_round="round1",
            to_round="round1",
        )
        self.assertFalse(payload["passed"])
        self.assertTrue(any("check_script" in item for item in payload["errors"]))

    def test_preflight_round1_passes_after_round0_with_codex_probe(self) -> None:
        Round0Initializer().initialize(
            project_root=self.config.project_root,
            notes_root=self.config.notes_root,
            course_id=self.config.course_id,
        )
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=FakeCodexExecutorWithProbe(default_success=True),  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )
        payload = orchestrator.preflight(
            project_root=self.config.project_root,
            from_round="round1",
            to_round="round1",
            target_lectures=["LEC01"],
        )
        self.assertTrue(payload["passed"])
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["warnings"], [])
        self.assertIn("round1", payload["context"]["rounds"])

    def test_preflight_returns_cancelled_when_probe_is_cancelled(self) -> None:
        Round0Initializer().initialize(
            project_root=self.config.project_root,
            notes_root=self.config.notes_root,
            course_id=self.config.course_id,
        )
        orchestrator = WorkflowOrchestrator(
            project_service=self.project_service,
            codex_executor=FakeCodexExecutorWithProbe(default_success=True),  # type: ignore[arg-type]
            check_runner=FakeCheckRunner(outcomes=[True]),  # type: ignore[arg-type]
            round0_initializer=Round0Initializer(),
        )

        payload = orchestrator.preflight(
            project_root=self.config.project_root,
            from_round="round1",
            to_round="round1",
            cancel_check=lambda: True,
        )
        self.assertFalse(payload["passed"])
        self.assertTrue(payload["cancelled"])
        self.assertIn("cancelled by user", payload["errors"])


if __name__ == "__main__":
    unittest.main()
