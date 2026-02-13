from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ExportFormat = Literal["json", "markdown"]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class PromptSummary(BaseModel):
    id: int
    title: str
    updated_at: str
    is_deleted: bool
    tags: list[str] = Field(default_factory=list)


class PromptDetail(BaseModel):
    id: int
    title: str
    body: str
    created_at: str
    updated_at: str
    is_deleted: bool
    tags: list[str] = Field(default_factory=list)


class PromptListResponse(BaseModel):
    items: list[PromptSummary]
    total: int


class PromptUpsertRequest(BaseModel):
    title: str
    body: str
    tags: list[str] = Field(default_factory=list)


class PromptRenderRequest(BaseModel):
    variables: dict[str, str] = Field(default_factory=dict)


class PromptRenderResponse(BaseModel):
    content: str


class PromptCopyRequest(BaseModel):
    variables: dict[str, str] = Field(default_factory=dict)


class PromptCopyResponse(BaseModel):
    copied: bool
    content: str
    message: str


class PromptImportRequest(BaseModel):
    input_path: str


class PromptImportResponse(BaseModel):
    added: int
    skipped: int


class PromptExportRequest(BaseModel):
    format: ExportFormat
    output_path: str
    include_deleted: bool = False


class PromptExportResponse(BaseModel):
    output_path: str
    format: ExportFormat

