"""小红书数据接入 — Pydantic 输出模型（契约）"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class XhsNote(BaseModel):
    id: str
    note_url: str | None = None
    title: str | None = None
    content: str | None = None
    publish_time: str | None = None
    likes: int | None = None
    collects: int | None = None
    comments: int | None = None
    views: int | None = None
    tags: list[str] = Field(default_factory=list)
    query_keyword: str | None = None
    captured_at: str | None = None
    source_type: str = "xhs"
    source_url: str | None = None


class IngestRequest(BaseModel):
    """批量导入请求：paths 为本地文件绝对/相对路径列表。"""
    paths: list[str]
    keyword: str | None = None


class IngestSummary(BaseModel):
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    invalid: int = 0
    total: int = 0


class IngestResult(BaseModel):
    summary: IngestSummary
    runs: list[dict[str, Any]] = Field(default_factory=list)


class Engagement(BaseModel):
    note_count: int
    likes: int = 0
    collects: int = 0
    comments: int = 0
    interactions: int = 0
    engagement_rate: float | None = None
    basis: str
    views: int | None = None
