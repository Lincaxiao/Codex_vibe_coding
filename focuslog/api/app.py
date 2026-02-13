from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..db import default_db_path
from .routes.export import router as export_router
from .routes.health import router as health_router
from .routes.meta import router as meta_router
from .routes.report import router as report_router
from .routes.sessions import router as sessions_router
from .routes.stats import router as stats_router
from .routes.timer import router as timer_router
from .timer_service import timer_service


def create_app(
    db_path: Path | None = None,
    frontend_dist: Path | None = None,
    dev_url: str | None = None,
) -> FastAPI:
    resolved_db = Path(db_path or default_db_path())
    timer_service.configure(resolved_db)

    app = FastAPI(title="FocusLog API", version="1.1.0")
    app.state.db_path = str(resolved_db)

    app.include_router(health_router)
    app.include_router(meta_router)
    app.include_router(sessions_router)
    app.include_router(stats_router)
    app.include_router(report_router)
    app.include_router(export_router)
    app.include_router(timer_router)

    if dev_url:
        app.add_api_route("/", lambda: HTMLResponse(_dev_html(dev_url)), methods=["GET"])
    elif frontend_dist and (frontend_dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
    else:
        app.add_api_route("/", lambda: HTMLResponse(_missing_frontend_html()), methods=["GET"])

    return app


def create_default_app() -> FastAPI:
    frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    dev_url = os.environ.get("FOCUSLOG_DEV_URL", "").strip() or None
    return create_app(db_path=default_db_path(), frontend_dist=frontend_dist, dev_url=dev_url)


def _missing_frontend_html() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>FocusLog</title>
    <style>
      body { font-family: "Microsoft YaHei", sans-serif; margin: 0; padding: 2rem; background: #f6f8fb; color: #111827; }
      code { background: #e5e7eb; padding: 0.2rem 0.4rem; border-radius: 0.25rem; }
      .card { max-width: 760px; margin: 2rem auto; background: white; border: 1px solid #e5e7eb; border-radius: 0.75rem; padding: 1.25rem; }
    </style>
  </head>
  <body>
    <div class="card">
      <h1>FocusLog 前端未构建</h1>
      <p>请先在仓库根目录执行以下命令：</p>
      <p><code>npm --prefix focuslog/frontend install</code></p>
      <p><code>npm --prefix focuslog/frontend run build</code></p>
      <p>然后重新启动 GUI。</p>
    </div>
  </body>
</html>
"""


def _dev_html(dev_url: str) -> str:
    return f"""
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta http-equiv="refresh" content="0; url={dev_url}" />
    <title>FocusLog</title>
  </head>
  <body>
    正在跳转到前端开发服务：{dev_url}
  </body>
</html>
"""


app = create_default_app()

