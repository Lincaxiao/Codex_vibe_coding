from __future__ import annotations

import io
from pathlib import Path
import unittest

from focuslog import cli
from focuslog.tests.test_helpers import local_tmp_dir


class TestCLI(unittest.TestCase):
    def test_start_rejects_negative_tick_seconds(self) -> None:
        with local_tmp_dir() as tmp:
            db_path = Path(tmp) / "focuslog.sqlite"
            args = [
                "--db",
                str(db_path),
                "start",
                "--work",
                "1",
                "--break",
                "0",
                "--long-break",
                "0",
                "--cycles",
                "1",
                "--tick-seconds",
                "-1",
            ]

            with self.assertRaises(SystemExit) as exc:
                cli.main(args)

            self.assertEqual(exc.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
