from __future__ import annotations

from pathlib import Path
from threading import Thread
import time

from ..db import default_db_path


def launch_desktop(
    db_path: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 18490,
) -> int:
    try:
        import fastapi  # noqa: F401
    except Exception:
        print("缺少 fastapi，请先安装：pip install fastapi")
        return 2

    try:
        import uvicorn
    except Exception:
        print("缺少 uvicorn，请先安装：pip install uvicorn")
        return 2

    try:
        import webview
    except Exception:
        print("缺少 pywebview，请先安装：pip install pywebview")
        return 2

    from ..api.app import create_app

    resolved_db = Path(db_path or default_db_path())
    app = create_app(resolved_db)

    def _run_api() -> None:
        uvicorn.run(app, host=host, port=port, log_level="warning")

    thread = Thread(target=_run_api, daemon=True)
    thread.start()
    time.sleep(0.6)

    webview.create_window("FocusLog", f"http://{host}:{port}", width=1100, height=760)
    webview.start()
    return 0

