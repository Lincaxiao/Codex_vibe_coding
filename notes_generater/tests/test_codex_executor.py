from __future__ import annotations

import json
import subprocess
import time
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
            CreateProjectRequest(course_id="executor-test", course_root=self.tmp_path / "workspace")
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

    def test_timeout_returns_exit_124(self) -> None:
        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            if cmd[:2] == ["codex", "--version"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="codex-cli 0.100.0-alpha.10\n", stderr="")
            if cmd[0] == "codex" and "exec" in cmd:
                raise subprocess.TimeoutExpired(
                    cmd=cmd,
                    timeout=kwargs.get("timeout", 0),
                    output="partial output",
                    stderr="",
                )
            raise AssertionError(f"unexpected command: {cmd}")

        with mock.patch("notes_agent.codex_executor.subprocess.run", side_effect=fake_run):
            result = self.executor.run(
                CodexRunRequest(
                    project_root=self.project_root,
                    notes_root=self.notes_root,
                    prompt="超时测试",
                    run_id="run_timeout",
                    max_retries=0,
                )
            )

        self.assertFalse(result.success)
        self.assertEqual(result.exit_code, 124)
        self.assertEqual(result.attempts, 1)
        self.assertIsNotNone(result.error)
        assert result.error is not None
        self.assertIn("timed out", result.error)

    def test_version_timeout_falls_back_to_unknown(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(cmd)
            if cmd[:2] == ["codex", "--version"]:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 0))
            if cmd[0] == "codex" and "exec" in cmd:
                output_path = Path(cmd[cmd.index("--output-last-message") + 1])
                output_path.write_text("ok\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, stdout="exec ok\n", stderr="")
            raise AssertionError(f"unexpected command: {cmd}")

        with mock.patch("notes_agent.codex_executor.subprocess.run", side_effect=fake_run):
            result = self.executor.run(
                CodexRunRequest(
                    project_root=self.project_root,
                    notes_root=self.notes_root,
                    prompt="版本超时回退",
                    run_id="run_version_timeout",
                )
            )

        self.assertTrue(result.success)
        manifest = json.loads(result.run_manifest_path.read_text(encoding="utf-8"))
        self.assertIn("unknown (timeout>", manifest["codex_cli_version"])

    def test_codex_not_found_returns_failed_result(self) -> None:
        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            if cmd[:2] == ["codex", "--version"]:
                raise FileNotFoundError("codex not found")
            if cmd[0] == "codex" and "exec" in cmd:
                raise FileNotFoundError("codex not found")
            raise AssertionError(f"unexpected command: {cmd}")

        with mock.patch("notes_agent.codex_executor.subprocess.run", side_effect=fake_run):
            result = self.executor.run(
                CodexRunRequest(
                    project_root=self.project_root,
                    notes_root=self.notes_root,
                    prompt="缺少 codex",
                    run_id="run_missing_codex",
                    max_retries=2,
                )
            )

        self.assertFalse(result.success)
        self.assertEqual(result.exit_code, 127)
        self.assertEqual(result.attempts, 1)
        self.assertIsNotNone(result.error)
        assert result.error is not None
        self.assertIn("failed to launch codex", result.error)

    def test_probe_cli_reports_unavailable_when_codex_missing(self) -> None:
        with mock.patch(
            "notes_agent.codex_executor.subprocess.run",
            side_effect=FileNotFoundError("codex not found"),
        ):
            payload = self.executor.probe_cli()
        self.assertFalse(payload["available"])
        self.assertIn("unavailable", payload["error"])

    def test_probe_cli_reports_cancelled(self) -> None:
        payload = self.executor.probe_cli(cancel_check=lambda: True)
        self.assertFalse(payload["available"])
        self.assertTrue(payload["cancelled"])
        self.assertEqual(payload["error"], "cancelled by user")

    def test_run_cancelled_before_attempt(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(cmd)
            if cmd[:2] == ["codex", "--version"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="codex-cli 0.100.0\n", stderr="")
            raise AssertionError("exec should not be called when cancelled before attempt")

        with mock.patch("notes_agent.codex_executor.subprocess.run", side_effect=fake_run):
            result = self.executor.run(
                CodexRunRequest(
                    project_root=self.project_root,
                    notes_root=self.notes_root,
                    prompt="取消测试",
                    run_id="run_cancel_before",
                    max_retries=1,
                ),
                cancel_check=lambda: True,
            )

        self.assertFalse(result.success)
        self.assertEqual(result.exit_code, 130)
        self.assertEqual(result.attempts, 1)
        self.assertTrue(any(cmd[:2] == ["codex", "--version"] for cmd in calls))

    def test_run_cancelled_during_exec(self) -> None:
        with mock.patch(
            "notes_agent.codex_executor.subprocess.run",
            return_value=subprocess.CompletedProcess(["codex", "--version"], 0, stdout="codex-cli 0.100.0\n", stderr=""),
        ), mock.patch.object(
            CodexExecutor,
            "_run_exec_with_cancel",
            return_value=(130, "cancelled by user", False, True, None),
        ):
            result = self.executor.run(
                CodexRunRequest(
                    project_root=self.project_root,
                    notes_root=self.notes_root,
                    prompt="取消测试",
                    run_id="run_cancel_during",
                    max_retries=0,
                ),
                cancel_check=lambda: False,
            )

        self.assertFalse(result.success)
        self.assertEqual(result.exit_code, 130)
        self.assertEqual(result.error, "cancelled by user")

    def test_run_exec_with_cancel_handles_large_output_without_false_timeout(self) -> None:
        command = [
            "python3",
            "-c",
            "import sys; sys.stdout.write('x' * (2 * 1024 * 1024)); sys.stdout.flush()",
        ]
        exit_code, stdio, timed_out, cancelled, launch_error = self.executor._run_exec_with_cancel(
            command=command,
            cwd=self.project_root,
            timeout_seconds=5,
            cancel_check=lambda: False,
        )
        self.assertEqual(exit_code, 0)
        self.assertFalse(timed_out)
        self.assertFalse(cancelled)
        self.assertIsNone(launch_error)
        self.assertGreater(len(stdio), 1500 * 1024)

    def test_run_emits_progress_messages(self) -> None:
        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            if cmd[:2] == ["codex", "--version"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="codex-cli 0.100.0-alpha.10\n", stderr="")
            if cmd[0] == "codex" and "exec" in cmd:
                output_path = Path(cmd[cmd.index("--output-last-message") + 1])
                output_path.write_text("ok\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, stdout="done\n", stderr="")
            raise AssertionError(f"unexpected command: {cmd}")

        messages: list[str] = []
        with mock.patch("notes_agent.codex_executor.subprocess.run", side_effect=fake_run):
            result = self.executor.run(
                CodexRunRequest(
                    project_root=self.project_root,
                    notes_root=self.notes_root,
                    prompt="进度日志测试",
                    run_id="run_progress",
                ),
                progress_callback=messages.append,
            )

        self.assertTrue(result.success)
        self.assertTrue(any("启动 run_id=run_progress" in item for item in messages))
        self.assertTrue(any("attempt 1/" in item and "开始" in item for item in messages))
        self.assertTrue(any("attempt 1 成功" in item for item in messages))
        self.assertTrue(any("结束 success=True" in item for item in messages))

    def test_run_includes_extra_allowed_dirs(self) -> None:
        calls: list[list[str]] = []
        extra_dir = self.tmp_path / "course_data" / "LEC01"
        extra_dir.mkdir(parents=True, exist_ok=True)

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            calls.append(cmd)
            if cmd[:2] == ["codex", "--version"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="codex-cli 0.100.0-alpha.10\n", stderr="")
            if cmd[0] == "codex" and "exec" in cmd:
                output_path = Path(cmd[cmd.index("--output-last-message") + 1])
                output_path.write_text("ok\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")
            raise AssertionError(f"unexpected command: {cmd}")

        with mock.patch("notes_agent.codex_executor.subprocess.run", side_effect=fake_run):
            result = self.executor.run(
                CodexRunRequest(
                    project_root=self.project_root,
                    notes_root=self.notes_root,
                    prompt="读取讲次目录",
                    run_id="run_extra_dir",
                    extra_allowed_dirs=[extra_dir],
                )
            )

        self.assertTrue(result.success)
        exec_command = next(cmd for cmd in calls if cmd[0] == "codex" and "exec" in cmd)
        add_dir_values = [exec_command[idx + 1] for idx, token in enumerate(exec_command) if token == "--add-dir"]
        self.assertIn(str(self.notes_root), add_dir_values)
        self.assertIn(str(extra_dir.resolve()), add_dir_values)

    def test_run_emits_heartbeat_when_execution_is_slow(self) -> None:
        executor = CodexExecutor(exec_timeout_seconds=30, progress_interval_seconds=0.01)

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            if cmd[:2] == ["codex", "--version"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="codex-cli 0.100.0-alpha.10\n", stderr="")
            if cmd[0] == "codex" and "exec" in cmd:
                time.sleep(0.05)
                output_path = Path(cmd[cmd.index("--output-last-message") + 1])
                output_path.write_text("ok\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")
            raise AssertionError(f"unexpected command: {cmd}")

        messages: list[str] = []
        with mock.patch("notes_agent.codex_executor.subprocess.run", side_effect=fake_run):
            result = executor.run(
                CodexRunRequest(
                    project_root=self.project_root,
                    notes_root=self.notes_root,
                    prompt="慢执行心跳",
                    run_id="run_heartbeat",
                    max_retries=0,
                ),
                progress_callback=messages.append,
            )

        self.assertTrue(result.success)
        self.assertTrue(any("理论最长约 30s" in item for item in messages))
        self.assertTrue(any("进行中，已等待" in item for item in messages))


if __name__ == "__main__":
    unittest.main()
