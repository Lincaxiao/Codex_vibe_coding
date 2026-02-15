from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from notes_agent.cache_service import CacheService
from notes_agent.models import CreateProjectRequest
from notes_agent.project_service import ProjectService


class CacheServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = TemporaryDirectory()
        self.tmp_path = Path(self._tmp_dir.name)
        self.project_service = ProjectService()
        self.cache_service = CacheService()
        self.config = self.project_service.create_project(
            CreateProjectRequest(course_id="cache-test", workspace_root=self.tmp_path / "workspace")
        )

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_clear_cache_removes_intermediate_files_but_keeps_notes(self) -> None:
        notes_file = self.config.notes_root / "notes" / "lectures" / "LEC01.md"
        notes_file.parent.mkdir(parents=True, exist_ok=True)
        notes_file.write_text("讲义正文\n", encoding="utf-8")

        run_dir = self.config.project_root / "runs" / "wf_a"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run_manifest.json").write_text("{}", encoding="utf-8")

        artifacts = self.config.project_root / "artifacts"
        (artifacts / "snapshots" / "snap1").mkdir(parents=True, exist_ok=True)
        (artifacts / "snapshots" / "snap1" / "a.txt").write_text("x\n", encoding="utf-8")
        (artifacts / "source_hashes.json").write_text("{}", encoding="utf-8")
        (artifacts / "prompt_templates.json").write_text("{}", encoding="utf-8")

        session_path = self.config.project_root / "state" / "session.json"
        session = json.loads(session_path.read_text(encoding="utf-8"))
        session["status"] = "running"
        session["current_run_id"] = "wf_a"
        session_path.write_text(json.dumps(session, ensure_ascii=False) + "\n", encoding="utf-8")

        result = self.cache_service.clear_intermediate_files(project_root=self.config.project_root)

        self.assertTrue(notes_file.exists())
        self.assertEqual(notes_file.read_text(encoding="utf-8"), "讲义正文\n")
        self.assertEqual(list((self.config.project_root / "runs").iterdir()), [])
        self.assertEqual(sorted(p.name for p in artifacts.iterdir()), ["prompt_templates.json"])
        self.assertTrue(result.session_reset)
        new_session = json.loads(session_path.read_text(encoding="utf-8"))
        self.assertEqual(new_session["status"], "idle")
        self.assertIsNone(new_session["current_run_id"])

    def test_clear_cache_can_remove_prompt_templates_when_disabled(self) -> None:
        prompt_path = self.config.project_root / "artifacts" / "prompt_templates.json"
        prompt_path.write_text("{}", encoding="utf-8")

        self.cache_service.clear_intermediate_files(
            project_root=self.config.project_root,
            preserve_prompt_templates=False,
        )
        self.assertFalse(prompt_path.exists())

    def test_clear_cache_emits_progress(self) -> None:
        messages: list[str] = []
        self.cache_service.clear_intermediate_files(
            project_root=self.config.project_root,
            progress_callback=messages.append,
        )
        self.assertTrue(any("[cache] 开始清理中间文件" in item for item in messages))
        self.assertTrue(any("[cache] 清理完成" in item for item in messages))


if __name__ == "__main__":
    unittest.main()

