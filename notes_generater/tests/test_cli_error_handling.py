from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

from notes_agent import cli


class CliErrorHandlingTests(unittest.TestCase):
    def test_run_workflow_catches_file_exists_error(self) -> None:
        argv = [
            "notes-agent",
            "run-workflow",
            "--project-root",
            "/tmp/project",
            "--workflow-run-id",
            "wf_dup",
        ]
        with mock.patch("sys.argv", argv), mock.patch.object(
            cli.WorkflowOrchestrator,
            "run",
            side_effect=FileExistsError("[Errno 17] File exists: /tmp/project/runs/wf_dup"),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.main()

        self.assertEqual(code, 2)
        payload = json.loads(buf.getvalue())
        self.assertIn("error", payload)
        self.assertIn("File exists", payload["error"])

    def test_resume_workflow_catches_file_exists_error(self) -> None:
        argv = [
            "notes-agent",
            "resume-workflow",
            "--project-root",
            "/tmp/project",
            "--workflow-run-id",
            "wf_dup",
        ]
        with mock.patch("sys.argv", argv), mock.patch.object(
            cli.WorkflowOrchestrator,
            "resume",
            side_effect=FileExistsError("[Errno 17] File exists: /tmp/project/runs/wf_dup"),
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.main()

        self.assertEqual(code, 2)
        payload = json.loads(buf.getvalue())
        self.assertIn("error", payload)
        self.assertIn("File exists", payload["error"])


if __name__ == "__main__":
    unittest.main()
