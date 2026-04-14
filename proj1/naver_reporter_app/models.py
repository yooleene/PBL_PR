"""Database models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, UniqueConstraint

from naver_reporter_app.extensions import db


class Reporter(db.Model):
    """Stored reporter identity and known Naver reporter page."""

    __tablename__ = "reporters"
    __table_args__ = (UniqueConstraint("office_name", "reporter_name", name="uq_reporter_identity"),)

    id = db.Column(db.Integer, primary_key=True)
    office_name = db.Column(db.String(255), nullable=False, index=True)
    reporter_name = db.Column(db.String(255), nullable=False, index=True)
    reporter_page_url = db.Column(db.String(1000), nullable=True)
    office_id = db.Column(db.String(50), nullable=True)
    last_collected_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    articles = db.relationship("Article", back_populates="reporter", lazy=True)
    analysis_runs = db.relationship("AnalysisRun", back_populates="reporter", lazy=True)


class Article(db.Model):
    """Collected news article data."""

    __tablename__ = "articles"

    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("reporters.id"), nullable=False, index=True)
    url = db.Column(db.String(1000), nullable=False, unique=True)
    title = db.Column(db.String(500), nullable=False)
    body = db.Column(db.Text, nullable=False)
    office_name = db.Column(db.String(255), nullable=False)
    reporter_name = db.Column(db.String(255), nullable=False)
    reporter_page_url = db.Column(db.String(1000), nullable=True)
    category = db.Column(db.String(255), nullable=True)
    published_date = db.Column(db.Date, nullable=False, index=True)
    collected_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    verified = db.Column(db.Boolean, nullable=False, default=False)
    source_type = db.Column(db.String(50), nullable=False, default="search")
    raw_metadata = db.Column(JSON, nullable=True)

    reporter = db.relationship("Reporter", back_populates="articles")


class AnalysisRun(db.Model):
    """Stores a single analysis execution."""

    __tablename__ = "analysis_runs"

    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("reporters.id"), nullable=False, index=True)
    requested_office_name = db.Column(db.String(255), nullable=False)
    requested_reporter_name = db.Column(db.String(255), nullable=False)
    date_from = db.Column(db.Date, nullable=False)
    date_to = db.Column(db.Date, nullable=False)
    requested_limit = db.Column(db.Integer, nullable=False)
    article_count = db.Column(db.Integer, nullable=False, default=0)
    reporter_page_url = db.Column(db.String(1000), nullable=True)
    status = db.Column(db.String(50), nullable=False, default="completed")
    search_queries = db.Column(JSON, nullable=False, default=list)
    fallback_used = db.Column(db.Boolean, nullable=False, default=False)
    analysis_result = db.Column(JSON, nullable=False, default=dict)
    warnings = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    reporter = db.relationship("Reporter", back_populates="analysis_runs")
