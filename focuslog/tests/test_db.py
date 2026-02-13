from __future__ import annotations

import sqlite3
import unittest

from focuslog.db import FocusLogDB
from focuslog.tests.test_helpers import local_tmp_dir


class TestDBSchema(unittest.TestCase):
    def test_schema_created(self) -> None:
        with local_tmp_dir() as tmp:
            db_path = tmp / "data" / "focuslog.sqlite"
            FocusLogDB(db_path)

            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
                ).fetchone()

            self.assertIsNotNone(row)


if __name__ == "__main__":
    unittest.main()
