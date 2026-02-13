from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .db import PromptDB, PromptRecord, normalize_tags
from .schemas import (
    HealthResponse,
    PromptCopyRequest,
    PromptCopyResponse,
    PromptDetail,
    PromptExportRequest,
    PromptExportResponse,
    PromptImportRequest,
    PromptImportResponse,
    PromptListResponse,
    PromptRenderRequest,
    PromptRenderResponse,
    PromptSummary,
    PromptUpsertRequest,
)
from .service import copy_to_clipboard, export_json, export_markdown, import_json, render_template


def create_app(db_path: Path | None = None, frontend_dist: Path | None = None, dev_url: str | None = None) -> FastAPI:
    db = PromptDB(Path(db_path) if db_path else None)
    db.init()

    app = FastAPI(title="Prompt Vault API", version="1.0.0")
    router = APIRouter(prefix="/api")

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @router.get("/prompts", response_model=PromptListResponse)
    def list_prompts(query: str = "", include_deleted: bool = False) -> PromptListResponse:
        records = db.search(query=query, include_deleted=include_deleted) if query.strip() else db.list_prompts(
            include_deleted=include_deleted
        )
        items = [_record_to_summary(db, rec) for rec in records]
        return PromptListResponse(items=items, total=len(items))

    @router.get("/prompts/{prompt_id}", response_model=PromptDetail)
    def get_prompt(prompt_id: int) -> PromptDetail:
        rec = db.get_prompt(prompt_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="未找到该提示词")
        return _record_to_detail(db, rec)

    @router.post("/prompts", response_model=PromptDetail)
    def create_prompt(payload: PromptUpsertRequest) -> PromptDetail:
        try:
            prompt_id = db.add_prompt(title=payload.title, body=payload.body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        tags = normalize_tags(payload.tags)
        if tags:
            db.set_tags(prompt_id, tags)

        rec = db.get_prompt(prompt_id)
        if rec is None:
            raise HTTPException(status_code=500, detail="创建后读取失败")
        return _record_to_detail(db, rec)

    @router.put("/prompts/{prompt_id}", response_model=PromptDetail)
    def update_prompt(prompt_id: int, payload: PromptUpsertRequest) -> PromptDetail:
        try:
            ok = db.update_prompt(prompt_id=prompt_id, title=payload.title, body=payload.body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not ok:
            raise HTTPException(status_code=404, detail="未找到该提示词")

        desired_tags = set(normalize_tags(payload.tags))
        current_tags = set(db.get_tags(prompt_id))
        add_tags = sorted(desired_tags - current_tags)
        remove_tags = sorted(current_tags - desired_tags)
        if add_tags:
            db.set_tags(prompt_id, add_tags)
        if remove_tags:
            db.remove_tags(prompt_id, remove_tags)

        rec = db.get_prompt(prompt_id)
        if rec is None:
            raise HTTPException(status_code=500, detail="更新后读取失败")
        return _record_to_detail(db, rec)

    @router.delete("/prompts/{prompt_id}")
    def delete_prompt(prompt_id: int) -> dict[str, Any]:
        ok = db.soft_delete(prompt_id)
        if not ok:
            raise HTTPException(status_code=404, detail="未找到该提示词")
        return {"ok": True}

    @router.post("/prompts/{prompt_id}/render", response_model=PromptRenderResponse)
    def render_prompt(prompt_id: int, payload: PromptRenderRequest) -> PromptRenderResponse:
        rec = db.get_prompt(prompt_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="未找到该提示词")
        content = render_template(rec.body, payload.variables)
        return PromptRenderResponse(content=content)

    @router.post("/prompts/{prompt_id}/copy", response_model=PromptCopyResponse)
    def copy_prompt(prompt_id: int, payload: PromptCopyRequest) -> PromptCopyResponse:
        rec = db.get_prompt(prompt_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="未找到该提示词")
        content = render_template(rec.body, payload.variables)
        copied = copy_to_clipboard(content)
        message = "已复制到剪贴板" if copied else "剪贴板不可用，请手动复制"
        return PromptCopyResponse(copied=copied, content=content, message=message)

    @router.post("/import", response_model=PromptImportResponse)
    def import_prompts(payload: PromptImportRequest) -> PromptImportResponse:
        path = Path(payload.input_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"文件不存在: {path}")
        try:
            added, skipped = import_json(db, path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return PromptImportResponse(added=added, skipped=skipped)

    @router.post("/export", response_model=PromptExportResponse)
    def export_prompts(payload: PromptExportRequest) -> PromptExportResponse:
        output_path = Path(payload.output_path)
        if payload.format == "json":
            export_json(db, output_path=output_path, include_deleted=payload.include_deleted)
        else:
            export_markdown(db, output_path=output_path, include_deleted=payload.include_deleted)
        return PromptExportResponse(output_path=str(output_path), format=payload.format)

    app.include_router(router)

    if dev_url:
        app.add_api_route("/", lambda: HTMLResponse(_dev_html(dev_url)), methods=["GET"])
    elif frontend_dist and (frontend_dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
    else:
        app.add_api_route("/", lambda: HTMLResponse(_missing_frontend_html()), methods=["GET"])

    return app


def _record_to_summary(db: PromptDB, rec: PromptRecord) -> PromptSummary:
    return PromptSummary(
        id=rec.id,
        title=rec.title,
        updated_at=rec.updated_at,
        is_deleted=bool(rec.is_deleted),
        tags=db.get_tags(rec.id),
    )


def _record_to_detail(db: PromptDB, rec: PromptRecord) -> PromptDetail:
    return PromptDetail(
        id=rec.id,
        title=rec.title,
        body=rec.body,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        is_deleted=bool(rec.is_deleted),
        tags=db.get_tags(rec.id),
    )


def _missing_frontend_html() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>Prompt Vault</title>
    <style>
      body { font-family: "Microsoft YaHei", sans-serif; margin: 0; padding: 2rem; background: #f6f8fb; color: #111827; }
      code { background: #e5e7eb; padding: 0.2rem 0.4rem; border-radius: 0.25rem; }
      .card { max-width: 760px; margin: 2rem auto; background: white; border: 1px solid #e5e7eb; border-radius: 0.75rem; padding: 1.25rem; }
    </style>
  </head>
  <body>
    <div class="card">
      <h1>Prompt Vault 前端未构建</h1>
      <p>请先在仓库根目录执行以下命令：</p>
      <p><code>npm --prefix prompt_vault/frontend install</code></p>
      <p><code>npm --prefix prompt_vault/frontend run build</code></p>
      <p>然后重新启动 <code>python -m prompt_vault gui</code>。</p>
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
    <title>Prompt Vault</title>
  </head>
  <body>
    正在跳转到前端开发服务：{dev_url}
  </body>
</html>
"""

