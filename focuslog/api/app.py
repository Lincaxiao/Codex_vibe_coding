from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from ..db import default_db_path
from .routes.export import router as export_router
from .routes.health import router as health_router
from .routes.meta import router as meta_router
from .routes.report import router as report_router
from .routes.sessions import router as sessions_router
from .routes.stats import router as stats_router
from .routes.timer import router as timer_router
from .timer_service import timer_service


def create_app(db_path: Path | None = None) -> FastAPI:
    resolved_db = Path(db_path or default_db_path())
    timer_service.configure(resolved_db)

    app = FastAPI(title="FocusLog API", version="1.1.0")
    app.state.db_path = str(resolved_db)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return """
        <html><head><meta charset='utf-8'><title>FocusLog Desktop</title></head>
        <body style='font-family:Segoe UI,Arial;padding:24px'>
          <h2>FocusLog Desktop API 已启动</h2>
          <p>当前为第二阶段实现，已支持 Timer SSE 事件流。</p>
          <p>可访问 <code>/docs</code> 查看 API。</p>
        </body></html>
        """

    app.include_router(health_router)
    app.include_router(meta_router)
    app.include_router(sessions_router)
    app.include_router(stats_router)
    app.include_router(report_router)
    app.include_router(export_router)
    app.include_router(timer_router)
    return app


app = create_app()

