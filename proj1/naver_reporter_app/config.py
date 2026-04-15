"""Application configuration."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _is_cloud_run() -> bool:
    """Return whether the app is running on Google Cloud Run."""
    return bool(os.getenv("K_SERVICE"))


def _build_default_sqlite_uri() -> str:
    """Select a writable SQLite path for the current runtime."""
    if _is_cloud_run():
        return "sqlite:////tmp/naver_reporter.db"
    return "sqlite:///naver_reporter.db"


def _normalize_database_uri(database_url: str | None) -> str:
    """Normalize provider-specific SQLAlchemy URLs."""
    if not database_url:
        return _build_default_sqlite_uri()
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql://", 1)
    return database_url


class Config:
    """Base configuration loaded from environment variables."""

    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret")
    SQLALCHEMY_DATABASE_URI = _normalize_database_uri(os.getenv("DATABASE_URL"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "5001"))
    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "12"))
    MAX_ARTICLES = int(os.getenv("MAX_ARTICLES", "20"))
    USER_AGENT = os.getenv(
        "USER_AGENT",
        "Mozilla/5.0 (compatible; NaverReporterAnalyzer/0.1; +prototype)",
    )
    ENABLE_PLAYWRIGHT_FALLBACK = os.getenv("ENABLE_PLAYWRIGHT_FALLBACK", "false").lower() == "true"
    PLAYWRIGHT_TIMEOUT_MS = int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "15000"))

    NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
    NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", "30"))

    REQUEST_DELAY_SECONDS = float(os.getenv("REQUEST_DELAY_SECONDS", "0.4"))
    SEARCH_PAGE_SIZE = int(os.getenv("SEARCH_PAGE_SIZE", "10"))
    SEARCH_MAX_PAGES = int(os.getenv("SEARCH_MAX_PAGES", "3"))
