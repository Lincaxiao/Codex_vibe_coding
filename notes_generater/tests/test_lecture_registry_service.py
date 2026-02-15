from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from notes_agent.lecture_registry_service import LectureRegistryService
from notes_agent.models import CreateProjectRequest
from notes_agent.project_service import ProjectService


class LectureRegistryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = TemporaryDirectory()
        self.tmp_path = Path(self._tmp_dir.name)
        self.project_service = ProjectService()
        self.config = self.project_service.create_project(
            CreateProjectRequest(course_root=self.tmp_path / "course", course_id="course")
        )
        self.service = LectureRegistryService()

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_upsert_accepts_multiple_paths(self) -> None:
        dir_path = self.tmp_path / "materials" / "LEC01"
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = self.tmp_path / "materials" / "lec01.pdf"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("stub\n", encoding="utf-8")

        entry = self.service.upsert_lecture(
            project_root=self.config.project_root,
            lec_id="LEC01",
            paths=[dir_path, file_path],
        )

        self.assertEqual(entry.lec_id, "LEC01")
        self.assertEqual(len(entry.paths), 2)
        listed = self.service.list_lectures(project_root=self.config.project_root)
        self.assertEqual([item.lec_id for item in listed], ["LEC01"])

    def test_upsert_rejects_invalid_lec_id(self) -> None:
        dir_path = self.tmp_path / "materials" / "LEC01"
        dir_path.mkdir(parents=True, exist_ok=True)

        with self.assertRaisesRegex(ValueError, "lec_id"):
            self.service.upsert_lecture(
                project_root=self.config.project_root,
                lec_id="../LEC01",
                paths=[dir_path],
            )

    def test_upsert_rejects_missing_path(self) -> None:
        missing = self.tmp_path / "not-exist"
        with self.assertRaisesRegex(FileNotFoundError, "path not found"):
            self.service.upsert_lecture(
                project_root=self.config.project_root,
                lec_id="LEC01",
                paths=[missing],
            )

    def test_resolve_paths_rejects_unknown_target(self) -> None:
        dir_path = self.tmp_path / "materials" / "LEC01"
        dir_path.mkdir(parents=True, exist_ok=True)
        self.service.upsert_lecture(
            project_root=self.config.project_root,
            lec_id="LEC01",
            paths=[dir_path],
        )

        with self.assertRaisesRegex(ValueError, "目标讲次未注册"):
            self.service.resolve_paths(
                project_root=self.config.project_root,
                target_lectures=["LEC404"],
            )

    def test_resolve_paths_without_target_returns_all_enabled_lectures(self) -> None:
        lec1 = self.tmp_path / "materials" / "LEC01"
        lec2 = self.tmp_path / "materials" / "LEC02"
        lec1.mkdir(parents=True, exist_ok=True)
        lec2.mkdir(parents=True, exist_ok=True)
        self.service.upsert_lecture(
            project_root=self.config.project_root,
            lec_id="LEC01",
            paths=[lec1],
        )
        self.service.upsert_lecture(
            project_root=self.config.project_root,
            lec_id="LEC02",
            paths=[lec2],
        )

        resolved = self.service.resolve_paths(project_root=self.config.project_root)
        self.assertEqual(sorted(resolved.keys()), ["LEC01", "LEC02"])


if __name__ == "__main__":
    unittest.main()
