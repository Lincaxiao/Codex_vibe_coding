from __future__ import annotations

import unittest

from notes_agent.models import ProjectConfig


class ProjectConfigModelTests(unittest.TestCase):
    def test_from_dict_parses_pause_after_each_round_string(self) -> None:
        payload = {
            "workspace_root": None,
            "course_id": "c1",
            "project_root": "/tmp/project",
            "notes_root": "/tmp/notes",
            "language": "zh-CN",
            "review_granularity": "lecture",
            "human_review_timing": "final_only",
            "pause_after_each_round": "false",
            "max_changed_lines": 500,
            "max_changed_files": 20,
            "network_mode": "disabled_by_default",
        }
        cfg = ProjectConfig.from_dict(payload)
        self.assertFalse(cfg.pause_after_each_round)

    def test_from_dict_parses_pause_after_each_round_true_string(self) -> None:
        payload = {
            "workspace_root": None,
            "course_id": "c1",
            "project_root": "/tmp/project",
            "notes_root": "/tmp/notes",
            "language": "zh-CN",
            "review_granularity": "lecture",
            "human_review_timing": "final_only",
            "pause_after_each_round": "true",
            "max_changed_lines": 500,
            "max_changed_files": 20,
            "network_mode": "disabled_by_default",
        }
        cfg = ProjectConfig.from_dict(payload)
        self.assertTrue(cfg.pause_after_each_round)


if __name__ == "__main__":
    unittest.main()
