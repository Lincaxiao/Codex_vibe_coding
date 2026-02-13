from __future__ import annotations

import os
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from ..db import default_db_path


def launch_desktop(db_path: Path | None = None) -> int:
    try:
        import uvicorn
        import webview
    except Exception as exc:
        print(f"GUI 启动失败：缺少依赖（fastapi/uvicorn/pywebview）。{exc}")
        print("请先安装依赖：pip install -r focuslog/requirements-gui.txt")
        print("推荐（Windows + conda）：focuslog/scripts/install_gui_deps.bat")
        return 2

    _enable_high_dpi()
    app = _create_api_app(db_path=db_path)
    host = "127.0.0.1"
    port = _find_free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    if not _wait_for_api(host, port, timeout_sec=12.0):
        print("GUI 启动失败：本地 API 未在预期时间内就绪。")
        return 2

    try:
        webview.create_window(
            "FocusLog",
            f"http://{host}:{port}",
            min_size=(1180, 760),
            text_select=True,
        )
        webview.start(**_webview_start_options())
    except Exception as exc:
        print(f"GUI 启动失败：{exc}")
        if os.name == "nt":
            print("请确认已安装 Microsoft Edge WebView2 Runtime，且可用。")
        return 2
    finally:
        server.should_exit = True
        thread.join(timeout=2.0)

    return 0


def _create_api_app(db_path: Path | None = None):
    from ..api.app import create_app

    resolved_db = Path(db_path or default_db_path())
    frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    dev_url = os.environ.get("FOCUSLOG_DEV_URL", "").strip() or None
    return create_app(db_path=resolved_db, frontend_dist=frontend_dist, dev_url=dev_url)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_for_api(host: str, port: int, timeout_sec: float) -> bool:
    deadline = time.time() + timeout_sec
    url = f"http://{host}:{port}/api/v1/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.2)
            continue
    return False


def _webview_start_options() -> dict[str, object]:
    options: dict[str, object] = {"debug": False}
    if os.name == "nt":
        # Force modern Edge runtime to avoid legacy engine fallback and CSS degradation.
        options["gui"] = "edgechromium"
    return options


def _enable_high_dpi() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        if hasattr(user32, "SetProcessDpiAwarenessContext"):
            user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            return
        shcore = ctypes.windll.shcore
        if hasattr(shcore, "SetProcessDpiAwareness"):
            shcore.SetProcessDpiAwareness(2)
            return
        if hasattr(user32, "SetProcessDPIAware"):
            user32.SetProcessDPIAware()
    except Exception:
        return

