from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class PromptVaultCLITest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.db = self.base / "data" / "prompt_vault.sqlite"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
        cmd = [sys.executable, "-m", "prompt_vault", "--db", str(self.db), *args]
        proc = subprocess.run(cmd, text=True, capture_output=True, cwd=Path(__file__).resolve().parents[2])
        if proc.returncode != expect:
            raise AssertionError(f"命令失败: {' '.join(cmd)}\nstdout={proc.stdout}\nstderr={proc.stderr}")
        return proc

    def test_db_creation(self) -> None:
        self.assertFalse(self.db.exists())
        self.run_cli("init")
        self.assertTrue(self.db.exists())

    def test_add_list_show(self) -> None:
        self.run_cli("add", "--title", "问候", "--body", "你好")
        listed = self.run_cli("list")
        self.assertIn("1\tactive\t问候", listed.stdout)
        shown = self.run_cli("show", "1")
        self.assertIn("标题: 问候", shown.stdout)
        self.assertIn("你好", shown.stdout)

    def test_tag_and_search(self) -> None:
        self.run_cli("add", "--title", "Python 帮手", "--body", "写脚本")
        self.run_cli("tag", "1", "--add", "python", "--add", "工具")
        result = self.run_cli("search", "python")
        self.assertIn("Python 帮手", result.stdout)
        result2 = self.run_cli("search", "工具")
        self.assertIn("Python 帮手", result2.stdout)

    def test_soft_delete_visibility(self) -> None:
        self.run_cli("add", "--title", "临时", "--body", "内容")
        self.run_cli("delete", "1")
        listed = self.run_cli("list")
        self.assertNotIn("临时", listed.stdout)
        listed_all = self.run_cli("list", "--all")
        self.assertIn("1\tdeleted\t临时", listed_all.stdout)

    def test_duplicate_add_rejected(self) -> None:
        self.run_cli("add", "--title", "重复", "--body", "相同正文")
        failed = self.run_cli("add", "--title", "重复", "--body", "相同正文", expect=1)
        self.assertIn("已存在相同标题与正文", failed.stderr)

    def test_render(self) -> None:
        self.run_cli("add", "--title", "模板", "--body", "你好 {{name}}")
        out = self.run_cli("render", "1", "--var", "name=世界")
        self.assertEqual(out.stdout.strip(), "你好 世界")

    def test_export_import_roundtrip(self) -> None:
        self.run_cli("add", "--title", "A", "--body", "B")
        self.run_cli("tag", "1", "--add", "x")
        export_path = self.base / "export.json"
        self.run_cli("export", "--format", "json", "--output", str(export_path))
        self.assertTrue(export_path.exists())

        second_db = self.base / "data" / "second.sqlite"
        cmd = [
            sys.executable,
            "-m",
            "prompt_vault",
            "--db",
            str(second_db),
            "import",
            "--input",
            str(export_path),
        ]
        proc = subprocess.run(cmd, text=True, capture_output=True, cwd=Path(__file__).resolve().parents[2])
        self.assertEqual(proc.returncode, 0, proc.stderr)

        list_cmd = [sys.executable, "-m", "prompt_vault", "--db", str(second_db), "list"]
        listed = subprocess.run(list_cmd, text=True, capture_output=True, cwd=Path(__file__).resolve().parents[2])
        self.assertIn("1\tactive\tA", listed.stdout)

        data = json.loads(export_path.read_text(encoding="utf-8"))
        self.assertEqual(data[0]["title"], "A")


if __name__ == "__main__":
    unittest.main()
