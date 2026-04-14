"""Naver search scraper."""

from __future__ import annotations

from html import unescape
from urllib.parse import urlparse

from bs4 import Tag
from flask import current_app

from naver_reporter_app.constants import (
    DEFAULT_SEARCH_QUERY_TEMPLATES,
    NAVER_NEWS_HOSTS,
    NAVER_OPEN_API_NEWS_URL,
    NAVER_SEARCH_URL,
)
from naver_reporter_app.schemas import SearchCandidate
from naver_reporter_app.scrapers.base import HttpFetcher


class NaverSearchScraper:
    """Search for candidate Naver news articles."""

    def __init__(self, fetcher: HttpFetcher | None = None) -> None:
        self.fetcher = fetcher or HttpFetcher()

    def build_queries(self, office_name: str, reporter_name: str) -> list[str]:
        return [
            template.format(office_name=office_name, reporter_name=reporter_name)
            for template in DEFAULT_SEARCH_QUERY_TEMPLATES
        ]

    def search_candidates(self, office_name: str, reporter_name: str) -> list[SearchCandidate]:
        queries = self.build_queries(office_name, reporter_name)
        seen_urls: set[str] = set()
        candidates: list[SearchCandidate] = []
        for query in queries:
            for candidate in self._search_query(query):
                if candidate.url in seen_urls:
                    continue
                seen_urls.add(candidate.url)
                candidates.append(candidate)
        return candidates

    def _search_query(self, query: str) -> list[SearchCandidate]:
        html_results = self._search_html(query)
        if html_results:
            return html_results
        return self._search_open_api(query)

    def _search_html(self, query: str) -> list[SearchCandidate]:
        page_size = current_app.config["SEARCH_PAGE_SIZE"]
        max_pages = current_app.config["SEARCH_MAX_PAGES"]
        candidates: list[SearchCandidate] = []
        for page_index in range(max_pages):
            start = page_index * page_size + 1
            fetch_result = self.fetcher.get(NAVER_SEARCH_URL, params={"where": "news", "query": query, "start": start})
            anchors = fetch_result.soup.select("a.news_tit, a.info, a[href*='news.naver.com'], a[href*='n.news.naver.com']")
            for anchor in anchors:
                href = self._extract_href(anchor)
                if href and self._is_news_url(href):
                    candidates.append(SearchCandidate(url=href, source_query=query))
        return candidates

    def _search_open_api(self, query: str) -> list[SearchCandidate]:
        client_id = current_app.config["NAVER_CLIENT_ID"]
        client_secret = current_app.config["NAVER_CLIENT_SECRET"]
        if not client_id or not client_secret:
            return []
        response = self.fetcher.session.get(
            NAVER_OPEN_API_NEWS_URL,
            params={"query": query, "display": 10, "sort": "date"},
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
            },
            timeout=current_app.config["REQUEST_TIMEOUT"],
        )
        response.raise_for_status()
        data = response.json()
        results: list[SearchCandidate] = []
        for item in data.get("items", []):
            link = unescape(item.get("originallink") or item.get("link") or "")
            if self._is_news_url(link):
                results.append(SearchCandidate(url=link, source_query=query))
        return results

    @staticmethod
    def _extract_href(anchor: Tag) -> str | None:
        href = anchor.get("href")
        if not href:
            return None
        if href.startswith("/"):
            return f"https://search.naver.com{href}"
        return href

    @staticmethod
    def _is_news_url(url: str) -> bool:
        return any(host in urlparse(url).netloc for host in NAVER_NEWS_HOSTS)
