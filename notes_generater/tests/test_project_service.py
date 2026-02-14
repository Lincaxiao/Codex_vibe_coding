from __future__ import annotations

import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from notes_agent.models import CreateProjectRequest
from notes_agent.project_service import ProjectService


class ProjectServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ProjectService()
        self._tmp_dir = TemporaryDirectory()
        self.tmp_path = Path(self._tmp_dir.name)

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_create_project_with_workspace_default_mapping(self) -> None:
        workspace_root = self.tmp_path / "workspace"

        config = self.service.create_project(
            CreateProjectRequest(course_id="CS 61A", workspace_root=workspace_root)
        )
        workspace_resolved = workspace_root.resolve()

        self.assertEqual(config.course_id, "cs-61a")
        self.assertEqual(config.project_root, workspace_resolved / "projects" / "cs-61a")
        self.assertEqual(config.notes_root, workspace_resolved / "notes" / "cs-61a")

        self.assertTrue((config.project_root / "project.yaml").exists())
        self.assertTrue((config.project_root / "state" / "session.json").exists())
        self.assertTrue((config.project_root / "state" / "round_status.json").exists())
        self.assertTrue((config.project_root / "runs").is_dir())
        self.assertTrue((config.project_root / "artifacts").is_dir())
        self.assertTrue(config.notes_root.is_dir())

        stored = json.loads((config.project_root / "project.yaml").read_text(encoding="utf-8"))
        self.assertEqual(stored["workspace_root"], str(workspace_resolved))
        self.assertEqual(stored["project_root"], str(config.project_root))
        self.assertEqual(stored["notes_root"], str(config.notes_root))

    def test_create_project_allows_explicit_roots(self) -> None:
        workspace_root = self.tmp_path / "workspace"
        explicit_project_root = self.tmp_path / "custom" / "project-root"
        explicit_notes_root = self.tmp_path / "custom" / "notes-root"

        config = self.service.create_project(
            CreateProjectRequest(
                course_id="machine-learning",
                workspace_root=workspace_root,
                project_root=explicit_project_root,
                notes_root=explicit_notes_root,
            )
        )

        self.assertEqual(config.project_root, explicit_project_root.resolve())
        self.assertEqual(config.notes_root, explicit_notes_root.resolve())
        self.assertTrue((config.project_root / "project.yaml").exists())
        self.assertTrue(config.notes_root.exists())

    def test_update_project_config(self) -> None:
        workspace_root = self.tmp_path / "workspace"
        config = self.service.create_project(
            CreateProjectRequest(course_id="nlp-101", workspace_root=workspace_root)
        )

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

    def test_discover_workspace_projects(self) -> None:
        workspace_root = self.tmp_path / "workspace"
        self.service.create_project(CreateProjectRequest(course_id="course-a", workspace_root=workspace_root))
        self.service.create_project(CreateProjectRequest(course_id="course-b", workspace_root=workspace_root))

        discovered = self.service.discover_workspace_projects(workspace_root)
        discovered_ids = [item.course_id for item in discovered]
        self.assertEqual(discovered_ids, ["course-a", "course-b"])

    def test_allow_existing_does_not_reset_state_files(self) -> None:
        workspace_root = self.tmp_path / "workspace"
        config = self.service.create_project(CreateProjectRequest(course_id="course-a", workspace_root=workspace_root))

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
            CreateProjectRequest(course_id="course-a", workspace_root=workspace_root),
            allow_existing=True,
        )

        self.assertEqual(json.loads(session_path.read_text(encoding="utf-8")), session_payload)
        self.assertEqual(json.loads(round_status_path.read_text(encoding="utf-8")), round_status_payload)


if __name__ == "__main__":
    unittest.main()
