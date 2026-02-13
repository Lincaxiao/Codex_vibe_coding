from __future__ import annotations

import json
import sqlite3
import unittest
import uuid
from pathlib import Path
import shutil


class PromptVaultAPITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            from fastapi.testclient import TestClient  # noqa: F401
        except Exception as exc:
            raise unittest.SkipTest(f"FastAPI 测试依赖缺失: {exc}") from exc

    def setUp(self) -> None:
        from fastapi.testclient import TestClient

        from prompt_vault.prompt_vault.api import create_app

        root_tmp = Path(__file__).resolve().parents[2] / "prompt_vault" / ".tmp_test"
        root_tmp.mkdir(parents=True, exist_ok=True)
        self.base = root_tmp / f"api_case_{uuid.uuid4().hex}"
        self.base.mkdir(parents=True, exist_ok=False)
        self.db_path = self.base / "data" / "prompt_vault.sqlite"
        self._ensure_sqlite_usable()

        app = create_app(db_path=self.db_path, frontend_dist=self.base / "not_exists")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        shutil.rmtree(self.base, ignore_errors=True)

    def _ensure_sqlite_usable(self) -> None:
        probe = self.base / "probe.sqlite"
        try:
            conn = sqlite3.connect(probe)
            conn.execute("CREATE TABLE IF NOT EXISTS t (x INTEGER)")
            conn.commit()
            conn.close()
        except sqlite3.Error as exc:
            self.skipTest(f"当前环境不可用 SQLite 文件写入: {exc}")

    def test_health(self) -> None:
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_create_list_render_and_delete(self) -> None:
        created = self.client.post(
            "/api/prompts",
            json={"title": "问候", "body": "你好 {{name}}", "tags": ["hello", "test"]},
        )
        self.assertEqual(created.status_code, 200)
        prompt_id = created.json()["id"]

        listed = self.client.get("/api/prompts")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["total"], 1)

        rendered = self.client.post(f"/api/prompts/{prompt_id}/render", json={"variables": {"name": "世界"}})
        self.assertEqual(rendered.status_code, 200)
        self.assertEqual(rendered.json()["content"], "你好 世界")

        deleted = self.client.delete(f"/api/prompts/{prompt_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["ok"])

    def test_import_export_roundtrip(self) -> None:
        payload = [
            {
                "title": "A",
                "body": "B",
                "tags": ["x"],
                "is_deleted": False,
            }
        ]
        import_json_path = self.base / "import.json"
        import_json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        imported = self.client.post("/api/import", json={"input_path": str(import_json_path)})
        self.assertEqual(imported.status_code, 200)
        self.assertEqual(imported.json()["added"], 1)

        export_json_path = self.base / "export.json"
        exported = self.client.post(
            "/api/export",
            json={"format": "json", "output_path": str(export_json_path), "include_deleted": True},
        )
        self.assertEqual(exported.status_code, 200)
        self.assertTrue(export_json_path.exists())

    def test_not_found(self) -> None:
        resp = self.client.get("/api/prompts/9999")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
