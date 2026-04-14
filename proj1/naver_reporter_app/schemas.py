"""Pydantic schemas."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnalyzeRequest(BaseModel):
    """Input payload for analysis."""

    office_name: str = Field(..., min_length=1, max_length=255)
    reporter_name: str = Field(..., min_length=1, max_length=255)
    date_from: date
    date_to: date
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("office_name", "reporter_name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("date_to")
    @classmethod
    def ensure_date_order(cls, value: date, info: Any) -> date:
        date_from = info.data.get("date_from")
        if date_from and value < date_from:
            raise ValueError("date_to must be greater than or equal to date_from")
        return value


class ArticleSchema(BaseModel):
    """Normalized article representation."""

    model_config = ConfigDict(from_attributes=True)

    url: str
    title: str
    body: str
    office_name: str
    reporter_name: str
    published_date: date
    reporter_page_url: str | None = None
    category: str | None = None
    verified: bool = False
    source_type: str = "search"
    special_label: str | None = None
    comment_count: int | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class ReporterSchema(BaseModel):
    """Reporter identity representation."""

    model_config = ConfigDict(from_attributes=True)

    office_name: str
    reporter_name: str
    reporter_page_url: str | None = None
    office_id: str | None = None


class AnalyzeResponse(BaseModel):
    """API response schema."""

    run_id: int
    reporter: ReporterSchema
    article_count: int
    articles: list[ArticleSchema] = Field(default_factory=list)
    analysis: dict[str, Any]
    posco_articles: list[dict[str, Any]] = Field(default_factory=list)
    popular_articles: list[dict[str, Any]] = Field(default_factory=list)
    llm_analysis: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class SearchCandidate(BaseModel):
    """Search candidate URL bundle."""

    url: str
    source_query: str


class ArticleParseResult(BaseModel):
    """Article parse result with verification metadata."""

    url: str
    title: str
    body: str
    published_date: date | None = None
    office_name: str | None = None
    reporter_name: str | None = None
    reporter_page_url: str | None = None
    category: str | None = None
    office_id: str | None = None
    verified: bool = False
    confidence_score: float = 0.0
    special_label: str | None = None
    comment_count: int | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class ReporterPageItem(BaseModel):
    """Reporter page listing item."""

    url: str
    title: str
    published_date: date | None = None
    category: str | None = None
    source_page: str | None = None
