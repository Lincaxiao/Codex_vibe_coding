from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from notes_agent.check_runner import CheckRunResult, CheckRunner
from notes_agent.codex_executor import CodexRunRequest, CodexRunResult
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

    def run(self, request: CodexRunRequest) -> CodexRunResult:
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


class RaisingCodexExecutor:
    def run(self, request: CodexRunRequest) -> CodexRunResult:
        raise RuntimeError("boom during codex execution")


class FakeCheckRunner:
    def __init__(self, outcomes: list[bool] | None = None) -> None:
        self.outcomes = outcomes or [True]
        self.calls = 0

    def run(self, *, project_root: Path | str, notes_root: Path | str, output_path: Path | str | None = None) -> CheckRunResult:
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
        self.config = self.project_service.create_project(
            CreateProjectRequest(course_id="workflow-test", workspace_root=self.tmp_path / "workspace")
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


if __name__ == "__main__":
    unittest.main()
