from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from notes_agent.feedback_service import FeedbackService


class FeedbackServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = TemporaryDirectory()
        self.tmp_path = Path(self._tmp_dir.name)
        self.notes_root = self.tmp_path / "notes_root"
        self.service = FeedbackService()

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_append_feedback(self) -> None:
        result = self.service.append_feedback(
            notes_root=self.notes_root,
            items=["术语解释需要补充", "增加一道练习题"],
            section_title="Round3 Review",
            author="tester",
        )
        self.assertTrue(result.feedback_path.exists())
        text = result.feedback_path.read_text(encoding="utf-8")
        self.assertIn("## Round3 Review", text)
        self.assertIn("- Author: tester", text)
        self.assertIn("- [ ] 术语解释需要补充", text)
        self.assertIn("- [ ] 增加一道练习题", text)

    def test_append_feedback_rejects_empty_items(self) -> None:
        with self.assertRaises(ValueError):
            self.service.append_feedback(notes_root=self.notes_root, items=[])


if __name__ == "__main__":
    unittest.main()
