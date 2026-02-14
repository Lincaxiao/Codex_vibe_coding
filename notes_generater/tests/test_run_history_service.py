from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from notes_agent.models import CreateProjectRequest
from notes_agent.project_service import ProjectService
from notes_agent.run_history_service import RunHistoryService


class RunHistoryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = TemporaryDirectory()
        self.tmp_path = Path(self._tmp_dir.name)
        self.project_service = ProjectService()
        self.config = self.project_service.create_project(
            CreateProjectRequest(course_id="history-test", workspace_root=self.tmp_path / "workspace")
        )
        self.service = RunHistoryService()

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_list_runs_with_workflow_and_codex(self) -> None:
        workflow_dir = self.config.project_root / "runs" / "wf_001"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        (workflow_dir / "workflow_result.json").write_text(
            json.dumps(
                {
                    "workflow_run_id": "wf_001",
                    "status": "succeeded",
                    "started_at": "2026-01-01T00:00:00+00:00",
                    "rounds": [1, 2],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        codex_dir = self.config.project_root / "runs" / "run_001"
        codex_dir.mkdir(parents=True, exist_ok=True)
        (codex_dir / "run_manifest.json").write_text(
            json.dumps(
                {
                    "success": True,
                    "created_at": "2026-01-01T00:01:00+00:00",
                    "attempts": [{"attempt": 1}],
                    "final_exit_code": 0,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        records = self.service.list_runs(project_root=self.config.project_root)
        self.assertEqual(len(records), 2)
        run_types = {item.run_type for item in records}
        self.assertIn("workflow", run_types)
        self.assertIn("codex", run_types)

    def test_latest_workflow_result(self) -> None:
        wf_dir = self.config.project_root / "runs" / "wf_002"
        wf_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "workflow_run_id": "wf_002",
            "status": "paused",
        }
        (wf_dir / "workflow_result.json").write_text(
            json.dumps(payload, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        latest = self.service.latest_workflow_result(project_root=self.config.project_root)
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest["workflow_run_id"], "wf_002")

    def test_load_round_status(self) -> None:
        path = self.config.project_root / "state" / "round_status.json"
        path.write_text(
            json.dumps({"round0": "completed", "round1": "paused"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        status = self.service.load_round_status(project_root=self.config.project_root)
        self.assertEqual(status["round0"], "completed")
        self.assertEqual(status["round1"], "paused")


if __name__ == "__main__":
    unittest.main()
