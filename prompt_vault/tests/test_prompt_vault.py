from __future__ import annotations

import io
import json
import sqlite3
import shutil
import unittest
import uuid
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path

from prompt_vault.prompt_vault.cli import main as cli_main


@dataclass
class CLIResult:
    returncode: int
    stdout: str
    stderr: str


class PromptVaultCLITest(unittest.TestCase):
    def setUp(self) -> None:
        root_tmp = Path(__file__).resolve().parents[2] / "prompt_vault" / ".tmp_test"
        root_tmp.mkdir(parents=True, exist_ok=True)
        self.base = root_tmp / f"case_{uuid.uuid4().hex}"
        self.base.mkdir(parents=True, exist_ok=False)
        self.db = self.base / "data" / "prompt_vault.sqlite"
        self._ensure_sqlite_usable()

    def tearDown(self) -> None:
        shutil.rmtree(self.base, ignore_errors=True)

    def _ensure_sqlite_usable(self) -> None:
        probe_path = self.base / "probe.sqlite"
        try:
            conn = sqlite3.connect(probe_path)
            conn.execute("CREATE TABLE IF NOT EXISTS t (x INTEGER)")
            conn.commit()
            conn.close()
        except sqlite3.Error as exc:
            self.skipTest(f"当前环境不可用 SQLite 文件写入: {exc}")

    def run_cli(self, *args: str, expect: int = 0, db: Path | None = None) -> CLIResult:
        stdout = io.StringIO()
        stderr = io.StringIO()
        db_path = db or self.db
        with redirect_stdout(stdout), redirect_stderr(stderr):
            returncode = cli_main(["--db", str(db_path), *args])
        result = CLIResult(returncode=returncode, stdout=stdout.getvalue(), stderr=stderr.getvalue())
        if result.returncode != expect:
            raise AssertionError(f"命令失败: {' '.join(args)}\nstdout={result.stdout}\nstderr={result.stderr}")
        return result

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
        self.run_cli("import", "--input", str(export_path), db=second_db)
        listed = self.run_cli("list", db=second_db)
        self.assertIn("1\tactive\tA", listed.stdout)

        data = json.loads(export_path.read_text(encoding="utf-8"))
        self.assertEqual(data[0]["title"], "A")


if __name__ == "__main__":
    unittest.main()
