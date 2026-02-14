from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from notes_agent.codex_executor import CodexExecutor, CodexRunRequest
from notes_agent.models import CreateProjectRequest
from notes_agent.project_service import ProjectService


class CodexExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = TemporaryDirectory()
        self.tmp_path = Path(self._tmp_dir.name)
        project_service = ProjectService()
        config = project_service.create_project(
            CreateProjectRequest(course_id="executor-test", workspace_root=self.tmp_path / "workspace")
        )
        self.project_root = config.project_root
        self.notes_root = config.notes_root
        self.executor = CodexExecutor()

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_run_success_writes_manifest_and_logs(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(cmd)
            if cmd[:2] == ["codex", "--version"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="codex-cli 0.100.0-alpha.10\n", stderr="")
            if cmd[0] == "codex" and "exec" in cmd:
                output_path = Path(cmd[cmd.index("--output-last-message") + 1])
                output_path.write_text("完成\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, stdout="exec ok\n", stderr="")
            raise AssertionError(f"unexpected command: {cmd}")

        with mock.patch("notes_agent.codex_executor.subprocess.run", side_effect=fake_run):
            result = self.executor.run(
                CodexRunRequest(
                    project_root=self.project_root,
                    notes_root=self.notes_root,
                    prompt="请输出一行测试文本",
                    run_id="run_success",
                )
            )

        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(result.prompt_path.exists())
        self.assertTrue(result.stdout_log_path.exists())
        self.assertTrue(result.last_message_path.exists())
        self.assertTrue(result.run_manifest_path.exists())

        manifest = json.loads(result.run_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["run_id"], "run_success")
        self.assertEqual(manifest["ask_for_approval_mode"], "never")
        self.assertEqual(manifest["sandbox_mode"], "workspace-write")
        self.assertTrue(manifest["success"])
        exec_command = next(cmd for cmd in calls if cmd[0] == "codex" and "exec" in cmd)
        self.assertEqual(exec_command[1:4], ["--ask-for-approval", "never", "exec"])

    def test_retry_on_retryable_failure(self) -> None:
        state = {"exec_calls": 0}

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            if cmd[:2] == ["codex", "--version"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="codex-cli 0.100.0-alpha.10\n", stderr="")
            if cmd[0] == "codex" and "exec" in cmd:
                state["exec_calls"] += 1
                if state["exec_calls"] == 1:
                    return subprocess.CompletedProcess(cmd, 1, stdout="network timeout\n", stderr="")
                output_path = Path(cmd[cmd.index("--output-last-message") + 1])
                output_path.write_text("第二次成功\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, stdout="ok after retry\n", stderr="")
            raise AssertionError(f"unexpected command: {cmd}")

        with mock.patch("notes_agent.codex_executor.subprocess.run", side_effect=fake_run):
            result = self.executor.run(
                CodexRunRequest(
                    project_root=self.project_root,
                    notes_root=self.notes_root,
                    prompt="重试测试",
                    run_id="run_retry",
                    max_retries=2,
                )
            )

        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.exit_code, 0)

        manifest = json.loads(result.run_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["attempts"]), 2)
        self.assertEqual(manifest["attempts"][0]["retry_reason"], "retryable_failure")

    def test_no_retry_on_non_retryable_failure(self) -> None:
        state = {"exec_calls": 0}

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            if cmd[:2] == ["codex", "--version"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="codex-cli 0.100.0-alpha.10\n", stderr="")
            if cmd[0] == "codex" and "exec" in cmd:
                state["exec_calls"] += 1
                return subprocess.CompletedProcess(cmd, 1, stdout="invalid argument\n", stderr="")
            raise AssertionError(f"unexpected command: {cmd}")

        with mock.patch("notes_agent.codex_executor.subprocess.run", side_effect=fake_run):
            result = self.executor.run(
                CodexRunRequest(
                    project_root=self.project_root,
                    notes_root=self.notes_root,
                    prompt="失败测试",
                    run_id="run_fail",
                    max_retries=2,
                )
            )

        self.assertFalse(result.success)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(state["exec_calls"], 1)

    def test_negative_max_retries_rejected(self) -> None:
        with mock.patch("notes_agent.codex_executor.subprocess.run") as mock_run:
            with self.assertRaisesRegex(ValueError, "max_retries must be >= 0"):
                self.executor.run(
                    CodexRunRequest(
                        project_root=self.project_root,
                        notes_root=self.notes_root,
                        prompt="失败测试",
                        run_id="run_negative_retries",
                        max_retries=-1,
                    )
                )
        mock_run.assert_not_called()

    def test_run_id_path_traversal_rejected(self) -> None:
        with mock.patch("notes_agent.codex_executor.subprocess.run") as mock_run:
            with self.assertRaisesRegex(ValueError, "run_id must be a single path component"):
                self.executor.run(
                    CodexRunRequest(
                        project_root=self.project_root,
                        notes_root=self.notes_root,
                        prompt="测试",
                        run_id="../escape",
                    )
                )
        mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
