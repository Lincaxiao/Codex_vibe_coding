from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from notes_agent.models import CreateProjectRequest
from notes_agent.project_service import PROJECT_REL_PATH, ProjectService


class ProjectServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ProjectService()
        self._tmp_dir = TemporaryDirectory()
        self.tmp_path = Path(self._tmp_dir.name)

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_create_project_from_course_root(self) -> None:
        course_root = self.tmp_path / "ECE364"

        config = self.service.create_project(
            CreateProjectRequest(course_root=course_root, course_id="ECE 364")
        )

        self.assertEqual(config.course_id, "ece-364")
        self.assertEqual(config.course_root, course_root.resolve())
        self.assertEqual(config.project_root, (course_root / PROJECT_REL_PATH).resolve())
        self.assertEqual(config.notes_root, (course_root / "notes").resolve())

        self.assertTrue((config.project_root / "project.yaml").exists())
        self.assertTrue((config.project_root / "state" / "session.json").exists())
        self.assertTrue((config.project_root / "state" / "round_status.json").exists())
        self.assertTrue((config.project_root / "runs").is_dir())
        self.assertTrue((config.project_root / "artifacts").is_dir())
        self.assertTrue(config.notes_root.is_dir())

        stored = json.loads((config.project_root / "project.yaml").read_text(encoding="utf-8"))
        self.assertEqual(stored["course_root"], str(config.course_root))
        self.assertEqual(stored["project_root"], str(config.project_root))
        self.assertEqual(stored["notes_root"], str(config.notes_root))
        self.assertNotIn("workspace_root", stored)

    def test_create_project_defaults_course_id_from_course_root_name(self) -> None:
        course_root = self.tmp_path / "Signal Processing 2026"
        config = self.service.create_project(CreateProjectRequest(course_root=course_root))
        self.assertEqual(config.course_id, "signal-processing-2026")

    def test_load_project_by_course_root(self) -> None:
        course_root = self.tmp_path / "course-a"
        created = self.service.create_project(CreateProjectRequest(course_root=course_root, course_id="course-a"))

        loaded = self.service.load_project_by_course_root(course_root)
        self.assertEqual(loaded.project_root, created.project_root)
        self.assertEqual(loaded.notes_root, created.notes_root)
        self.assertEqual(loaded.course_root, created.course_root)

    def test_update_project_config(self) -> None:
        course_root = self.tmp_path / "nlp-101"
        config = self.service.create_project(CreateProjectRequest(course_root=course_root, course_id="nlp-101"))

        updated = self.service.update_project_config(
            config.project_root,
            review_granularity="section",
            pause_after_each_round=True,
        )
        loaded = self.service.load_project_config(config.project_root)

        self.assertEqual(updated.review_granularity, "section")
        self.assertTrue(updated.pause_after_each_round)
        self.assertEqual(loaded.review_granularity, "section")
        self.assertTrue(loaded.pause_after_each_round)

    def test_allow_existing_does_not_reset_state_files(self) -> None:
        course_root = self.tmp_path / "course-a"
        config = self.service.create_project(CreateProjectRequest(course_root=course_root, course_id="course-a"))

        session_path = config.project_root / "state" / "session.json"
        round_status_path = config.project_root / "state" / "round_status.json"
        session_payload = {
            "course_id": config.course_id,
            "status": "paused",
            "current_run_id": "wf_existing",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-02T00:00:00+00:00",
        }
        round_status_payload = {
            "round0": "completed",
            "round1": "failed",
            "round2": "pending",
            "round3": "pending",
            "final": "pending",
        }
        session_path.write_text(json.dumps(session_payload, ensure_ascii=False) + "\n", encoding="utf-8")
        round_status_path.write_text(json.dumps(round_status_payload, ensure_ascii=False) + "\n", encoding="utf-8")

        self.service.create_project(
            CreateProjectRequest(course_root=course_root, course_id="course-a"),
            allow_existing=True,
        )

        self.assertEqual(json.loads(session_path.read_text(encoding="utf-8")), session_payload)
        self.assertEqual(json.loads(round_status_path.read_text(encoding="utf-8")), round_status_payload)

    def test_load_project_config_invalid_json_raises_value_error(self) -> None:
        course_root = self.tmp_path / "course-a"
        config = self.service.create_project(CreateProjectRequest(course_root=course_root, course_id="course-a"))
        (config.project_root / "project.yaml").write_text("{invalid-json\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "invalid project config"):
            self.service.load_project_config(config.project_root)


if __name__ == "__main__":
    unittest.main()
