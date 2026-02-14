from __future__ import annotations

import json
import os
import stat
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from notes_agent.models import CreateProjectRequest
from notes_agent.project_service import ProjectService
from notes_agent.snapshot_service import SnapshotService


def _make_tree_writable(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        try:
            if path.is_dir():
                os.chmod(path, 0o755)
            else:
                os.chmod(path, 0o644)
        except FileNotFoundError:
            continue
    try:
        os.chmod(root, 0o755)
    except FileNotFoundError:
        pass


class SnapshotServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = TemporaryDirectory()
        self.tmp_path = Path(self._tmp_dir.name)
        self.project_service = ProjectService()
        self.snapshot_service = SnapshotService()

    def tearDown(self) -> None:
        _make_tree_writable(self.tmp_path)
        self._tmp_dir.cleanup()

    def _create_project(self) -> Path:
        workspace_root = self.tmp_path / "workspace"
        config = self.project_service.create_project(
            CreateProjectRequest(course_id="cs-61a", workspace_root=workspace_root)
        )
        return config.project_root

    def test_create_snapshot_writes_index_and_hashes(self) -> None:
        project_root = self._create_project()
        source_root = self.tmp_path / "sources"
        source_root.mkdir(parents=True, exist_ok=True)

        slides_file = source_root / "lecture01.md"
        slides_file.write_text("# Intro\n", encoding="utf-8")

        code_dir = source_root / "code"
        code_dir.mkdir(parents=True, exist_ok=True)
        (code_dir / "main.py").write_text("print('hello')\n", encoding="utf-8")

        result = self.snapshot_service.create_snapshot(
            project_root=project_root,
            sources=[slides_file, code_dir],
            lecture_mapping={str(slides_file): "lecture-01"},
            snapshot_id="snap-001",
        )

        self.assertEqual(result.snapshot_id, "snap-001")
        self.assertEqual(result.source_count, 2)
        self.assertEqual(result.file_count, 2)
        self.assertTrue(result.source_index_path.exists())
        self.assertTrue(result.source_hashes_path.exists())

        source_index = json.loads(result.source_index_path.read_text(encoding="utf-8"))
        self.assertEqual(len(source_index["sources"]), 2)
        self.assertEqual(source_index["sources"][0]["lecture"], "lecture-01")

        source_hashes = json.loads(result.source_hashes_path.read_text(encoding="utf-8"))
        self.assertEqual(len(source_hashes["files"]), 2)

        snapshot_entries = list(result.snapshot_root.rglob("*"))
        self.assertTrue(any(entry.name.endswith("lecture01.md") for entry in snapshot_entries))
        self.assertTrue(any(entry.name == "main.py" for entry in snapshot_entries))

        mode_root = stat.S_IMODE(result.snapshot_root.stat().st_mode)
        self.assertEqual(mode_root, 0o555)

    def test_verify_snapshot_detects_hash_mismatch(self) -> None:
        project_root = self._create_project()
        source_file = self.tmp_path / "sources" / "lecture02.md"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("original\n", encoding="utf-8")

        result = self.snapshot_service.create_snapshot(
            project_root=project_root,
            sources=[source_file],
            snapshot_id="snap-002",
        )
        verified_ok = self.snapshot_service.verify_snapshot_hashes(project_root=project_root)
        self.assertTrue(verified_ok.valid)
        self.assertEqual(verified_ok.checked_files, 1)

        copied_file = next(path for path in result.snapshot_root.rglob("*") if path.is_file())
        os.chmod(copied_file.parent, 0o755)
        os.chmod(copied_file, 0o644)
        copied_file.write_text("mutated\n", encoding="utf-8")

        verified_bad = self.snapshot_service.verify_snapshot_hashes(project_root=project_root)
        self.assertFalse(verified_bad.valid)
        self.assertEqual(verified_bad.checked_files, 1)
        self.assertEqual(len(verified_bad.mismatches), 1)
        self.assertEqual(verified_bad.mismatches[0]["reason"], "hash_mismatch")

    def test_create_snapshot_with_missing_source_raises(self) -> None:
        project_root = self._create_project()
        missing_source = self.tmp_path / "missing" / "notfound.md"

        with self.assertRaises(FileNotFoundError):
            self.snapshot_service.create_snapshot(
                project_root=project_root,
                sources=[missing_source],
                snapshot_id="snap-003",
            )

    def test_snapshot_id_path_traversal_rejected(self) -> None:
        project_root = self._create_project()
        source_file = self.tmp_path / "sources" / "lecture03.md"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("ok\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "snapshot_id must be a single path component"):
            self.snapshot_service.create_snapshot(
                project_root=project_root,
                sources=[source_file],
                snapshot_id="../snap-escape",
            )

    def test_verify_snapshot_rejects_out_of_project_path(self) -> None:
        project_root = self._create_project()
        source_hashes_path = project_root / "artifacts" / "source_hashes.json"
        source_hashes_path.parent.mkdir(parents=True, exist_ok=True)
        source_hashes_path.write_text(
            json.dumps(
                {
                    "snapshot_id": "snap-malicious",
                    "files": {"../outside.txt": "deadbeef"},
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        verified = self.snapshot_service.verify_snapshot_hashes(project_root=project_root)
        self.assertFalse(verified.valid)
        self.assertEqual(verified.checked_files, 1)
        self.assertEqual(verified.mismatches[0]["reason"], "invalid_path")

    def test_verify_snapshot_handles_invalid_metadata_json(self) -> None:
        project_root = self._create_project()
        source_hashes_path = project_root / "artifacts" / "source_hashes.json"
        source_hashes_path.parent.mkdir(parents=True, exist_ok=True)
        source_hashes_path.write_text("{invalid-json\n", encoding="utf-8")

        verified = self.snapshot_service.verify_snapshot_hashes(project_root=project_root)
        self.assertFalse(verified.valid)
        self.assertEqual(verified.checked_files, 0)
        self.assertEqual(verified.mismatches[0]["reason"], "invalid_metadata")


if __name__ == "__main__":
    unittest.main()
