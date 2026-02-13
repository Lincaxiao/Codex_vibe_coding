from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from focuslog.db import FocusLogDB, SessionRecord
from focuslog.tests.test_helpers import local_tmp_dir


class TestAPI(unittest.TestCase):
    def setUp(self) -> None:
        try:
            from fastapi.testclient import TestClient  # noqa: F401
            from focuslog.api.app import create_app  # noqa: F401
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"fastapi test client unavailable: {exc}")

    def test_health_meta_sessions_and_openapi(self) -> None:
        from fastapi.testclient import TestClient

        from focuslog.api.app import create_app

        with local_tmp_dir() as tmp:
            db_path = tmp / "data" / "focuslog.sqlite"
            db = FocusLogDB(db_path)
            now = datetime.now(tz=timezone.utc)
            db.add_session(
                SessionRecord(
                    start_time=now,
                    end_time=now + timedelta(minutes=1),
                    duration_sec=60,
                    task="api测试",
                    tags="x,y",
                    kind="work",
                    completed=True,
                    interrupted_reason=None,
                )
            )

            client = TestClient(create_app(db_path=db_path))

            health = client.get("/api/v1/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json().get("status"), "ok")

            meta = client.get("/api/v1/meta")
            self.assertEqual(meta.status_code, 200)
            self.assertEqual(meta.json().get("db_path"), str(db_path))

            sessions = client.get("/api/v1/sessions")
            self.assertEqual(sessions.status_code, 200)
            items = sessions.json()
            self.assertTrue(items)

            detail = client.get(f"/api/v1/sessions/{items[0]['id']}")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.json()["task"], "api测试")

            missing = client.get("/api/v1/sessions/999999")
            self.assertEqual(missing.status_code, 404)

            start_bad = client.post("/api/v1/timer/start", json={"cycles": 0})
            self.assertEqual(start_bad.status_code, 422)

            openapi = client.get("/openapi.json")
            self.assertEqual(openapi.status_code, 200)
            paths = openapi.json().get("paths", {})
            self.assertIn("/api/v1/timer/stream", paths)


if __name__ == "__main__":
    unittest.main()
