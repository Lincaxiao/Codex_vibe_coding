from __future__ import annotations

import subprocess
import stat
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from notes_agent.check_runner import CheckRunner
from notes_agent.models import CreateProjectRequest
from notes_agent.project_service import ProjectService
from notes_agent.round0_initializer import Round0Initializer


class Round0AndCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = TemporaryDirectory()
        self.tmp_path = Path(self._tmp_dir.name)
        self.project_service = ProjectService()
        self.round0_initializer = Round0Initializer()
        self.check_runner = CheckRunner()
        config = self.project_service.create_project(
            CreateProjectRequest(course_id="round0-test", workspace_root=self.tmp_path / "workspace")
        )
        self.project_root = config.project_root
        self.notes_root = config.notes_root

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_round0_initializer_creates_required_files(self) -> None:
        result = self.round0_initializer.initialize(
            project_root=self.project_root,
            notes_root=self.notes_root,
            course_id="round0-test",
        )
        self.assertGreater(len(result.created_files), 0)

        required = [
            self.notes_root / "index" / "manifest.yml",
            self.notes_root / "index" / "questions_backlog.md",
            self.notes_root / "index" / "glossary.md",
            self.notes_root / "notes" / "cheatsheet.md",
            self.notes_root / "notes" / "lectures" / "README.md",
            self.notes_root / "review" / "feedback.md",
            self.notes_root / "review" / "rubric.md",
            self.notes_root / "scripts" / "check_notes.py",
            self.notes_root / "scripts" / "check.sh",
        ]
        for path in required:
            self.assertTrue(path.exists(), str(path))

        mode = stat.S_IMODE((self.notes_root / "scripts" / "check.sh").stat().st_mode)
        self.assertEqual(mode, 0o755)

    def test_check_runner_passes_after_round0(self) -> None:
        self.round0_initializer.initialize(
            project_root=self.project_root,
            notes_root=self.notes_root,
            course_id="round0-test",
        )
        result = self.check_runner.run(
            project_root=self.project_root,
            notes_root=self.notes_root,
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.exit_code, 0)
        self.assertIsNotNone(result.payload)
        assert result.payload is not None
        self.assertTrue(result.payload["passed"])

    def test_check_runner_fails_for_low_chinese_ratio(self) -> None:
        self.round0_initializer.initialize(
            project_root=self.project_root,
            notes_root=self.notes_root,
            course_id="round0-test",
        )
        lecture_file = self.notes_root / "notes" / "lectures" / "lecture01.md"
        lecture_file.write_text(
            "# Lecture 01\n\n"
            "This lecture note is intentionally written in English only so that the checker fails. "
            "It has enough length to exceed the threshold and should trigger low Chinese ratio.\n",
            encoding="utf-8",
        )

        result = self.check_runner.run(
            project_root=self.project_root,
            notes_root=self.notes_root,
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 1)
        self.assertIsNotNone(result.payload)
        assert result.payload is not None
        self.assertFalse(result.payload["passed"])
        errors = result.payload["errors"]
        self.assertTrue(any("low Chinese ratio" in item for item in errors))

    def test_check_runner_timeout_returns_failed_result(self) -> None:
        self.round0_initializer.initialize(
            project_root=self.project_root,
            notes_root=self.notes_root,
            course_id="round0-test",
        )

        with mock.patch(
            "notes_agent.check_runner.subprocess.run",
            side_effect=subprocess.TimeoutExpired(
                cmd=["check.sh", str(self.project_root)],
                timeout=1,
                output="partial stdout",
                stderr="partial stderr",
            ),
        ):
            result = self.check_runner.run(
                project_root=self.project_root,
                notes_root=self.notes_root,
            )

        self.assertFalse(result.passed)
        self.assertEqual(result.exit_code, 124)
        self.assertIsNone(result.payload)
        self.assertIn("timed out", result.stderr)


if __name__ == "__main__":
    unittest.main()
