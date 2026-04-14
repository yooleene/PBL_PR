"""Application configuration."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration loaded from environment variables."""

    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///naver_reporter.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

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
