"""HTTP fetching utilities with retry, timeout, and optional Playwright fallback."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests
from bs4 import BeautifulSoup
from flask import current_app
from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """Response wrapper used by scrapers."""

    url: str
    text: str
    status_code: int
    final_url: str

    @property
    def soup(self) -> BeautifulSoup:
        return BeautifulSoup(self.text, "lxml")


class HttpFetcher:
    """Shared fetcher for Naver scraping.

    Respect robots.txt and Terms of Service before using this beyond prototyping.
    """

    def __init__(self) -> None:
        self._session: Session | None = None

    def _build_session(self) -> Session:
        retry = Retry(
            total=3,
            read=3,
            connect=3,
            status=3,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "HEAD"),
            raise_on_status=False,
        )
        session = requests.Session()
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update(
            {
                "User-Agent": current_app.config["USER_AGENT"],
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )
        return session

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = self._build_session()
        return self._session

    def get(self, url: str, *, params: dict[str, Any] | None = None) -> FetchResult:
        """Fetch a URL with retry and optional Playwright fallback."""
        response = self.session.get(url, params=params, timeout=current_app.config["REQUEST_TIMEOUT"])
        time.sleep(current_app.config["REQUEST_DELAY_SECONDS"])
        if response.ok:
            return self._to_result(response)
        if current_app.config["ENABLE_PLAYWRIGHT_FALLBACK"]:
            fallback = self._fetch_with_playwright(url)
            if fallback is not None:
                return fallback
        response.raise_for_status()
        return self._to_result(response)

    def _to_result(self, response: Response) -> FetchResult:
        return FetchResult(
            url=str(response.url),
            text=response.text,
            status_code=response.status_code,
            final_url=str(response.url),
        )

    def _fetch_with_playwright(self, url: str) -> FetchResult | None:
        """Fallback renderer for dynamic pages."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return None
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(user_agent=current_app.config["USER_AGENT"])
                page.goto(url, wait_until="networkidle", timeout=current_app.config["PLAYWRIGHT_TIMEOUT_MS"])
                html = page.content()
                final_url = page.url
                browser.close()
            return FetchResult(url=url, text=html, status_code=200, final_url=final_url)
        except Exception as exc:  # pragma: no cover - browser/runtime specific path
            logger.warning("Playwright fallback is unavailable for %s: %s", url, exc)
            return None
