from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from notes_agent.diff_service import DiffService


class DiffServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = TemporaryDirectory()
        self.tmp_path = Path(self._tmp_dir.name)
        self.notes_root = self.tmp_path / "notes"
        self.notes_root.mkdir(parents=True, exist_ok=True)
        self.run_dir = self.tmp_path / "run"
        self.service = DiffService()

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_write_diff_artifacts_for_add_modify_delete(self) -> None:
        file_a = self.notes_root / "notes" / "lectures" / "a.md"
        file_b = self.notes_root / "notes" / "lectures" / "b.md"
        file_a.parent.mkdir(parents=True, exist_ok=True)
        file_a.write_text("line1\nline2\n", encoding="utf-8")
        file_b.write_text("old-b\n", encoding="utf-8")

        before = self.service.capture_state(notes_root=self.notes_root)

        file_a.write_text("line1\nline2-mod\n", encoding="utf-8")
        file_b.unlink()
        file_c = self.notes_root / "notes" / "lectures" / "c.md"
        file_c.write_text("new-c\n", encoding="utf-8")

        after = self.service.capture_state(notes_root=self.notes_root)
        summary = self.service.write_diff_artifacts(
            notes_root=self.notes_root,
            before_state=before,
            after_state=after,
            run_dir=self.run_dir,
        )

        self.assertEqual(summary.changed_files, 3)
        self.assertTrue(summary.patch_path.exists())
        self.assertTrue(summary.notes_snapshot_path.exists())
        self.assertGreater(summary.changed_lines, 0)
        self.assertIn("notes/lectures/a.md", summary.changed_rel_paths)
        self.assertIn("notes/lectures/b.md", summary.changed_rel_paths)
        self.assertIn("notes/lectures/c.md", summary.changed_rel_paths)

        patch_text = summary.patch_path.read_text(encoding="utf-8")
        self.assertIn("a/notes/lectures/a.md", patch_text)
        self.assertIn("b/notes/lectures/a.md", patch_text)
        self.assertIn("a/notes/lectures/b.md", patch_text)
        self.assertIn("b/notes/lectures/c.md", patch_text)

        self.assertTrue((summary.notes_snapshot_path / "notes" / "lectures" / "a.md").exists())
        self.assertTrue((summary.notes_snapshot_path / "notes" / "lectures" / "c.md").exists())
        deleted_manifest = summary.notes_snapshot_path / "deleted_files.json"
        self.assertTrue(deleted_manifest.exists())
        deleted_payload = json.loads(deleted_manifest.read_text(encoding="utf-8"))
        self.assertIn("notes/lectures/b.md", deleted_payload["deleted_files"])

    def test_capture_state_ignores_symlink_to_outside(self) -> None:
        outside = self.tmp_path / "outside.txt"
        outside.write_text("outside\n", encoding="utf-8")

        safe_file = self.notes_root / "notes" / "lectures" / "safe.md"
        safe_file.parent.mkdir(parents=True, exist_ok=True)
        safe_file.write_text("safe\n", encoding="utf-8")

        symlink_path = self.notes_root / "notes" / "lectures" / "outside_link.md"
        os.symlink(outside, symlink_path)

        state = self.service.capture_state(notes_root=self.notes_root)
        self.assertIn("notes/lectures/safe.md", state)
        self.assertNotIn("notes/lectures/outside_link.md", state)


if __name__ == "__main__":
    unittest.main()
