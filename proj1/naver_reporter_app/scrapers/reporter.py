"""Reporter page scraping."""

from __future__ import annotations

from collections import Counter
from datetime import date
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from bs4 import Tag

from naver_reporter_app.constants import NAVER_SELECTORS, REPORTER_DIRECTORY_PATTERNS
from naver_reporter_app.schemas import ArticleParseResult, ReporterPageItem
from naver_reporter_app.scrapers.base import HttpFetcher
from naver_reporter_app.utils.text import extract_date, names_match, normalize_whitespace


class NaverReporterScraper:
    """Scrape reporter page items and find reporter page fallbacks."""

    def __init__(self, fetcher: HttpFetcher | None = None) -> None:
        self.fetcher = fetcher or HttpFetcher()

    def select_representative_reporter_url(self, articles: list[ArticleParseResult]) -> str | None:
        urls = [article.reporter_page_url for article in articles if article.reporter_page_url]
        return Counter(urls).most_common(1)[0][0] if urls else None

    def crawl_reporter_articles(
        self,
        reporter_page_url: str,
        *,
        date_from: date,
        date_to: date,
        limit: int,
    ) -> list[ReporterPageItem]:
        items: list[ReporterPageItem] = []
        seen_urls: set[str] = set()
        visited_pages: set[str] = set()
        next_url = reporter_page_url
        page_number = 1
        while next_url and len(items) < limit and page_number <= 5:
            if next_url in visited_pages:
                break
            visited_pages.add(next_url)
            fetch_result = self.fetcher.get(next_url)
            page_items = self._parse_reporter_page(fetch_result.final_url, fetch_result.soup)
            for item in page_items:
                if item.url in seen_urls:
                    continue
                if item.published_date and (item.published_date < date_from or item.published_date > date_to):
                    continue
                seen_urls.add(item.url)
                items.append(item)
                if len(items) >= limit:
                    break
            next_url = self._next_page_url(fetch_result.final_url, fetch_result.soup, page_number)
            page_number += 1
        return items[:limit]

    def find_reporter_page_from_office_directory(self, *, office_id: str | None, reporter_name: str) -> str | None:
        if not office_id:
            return None
        for pattern in REPORTER_DIRECTORY_PATTERNS:
            fetch_result = self.fetcher.get(pattern.format(office_id=office_id))
            for anchor in fetch_result.soup.select("a[href*='/journalist/'], a[href*='/reporter/']"):
                href = anchor.get("href")
                text = normalize_whitespace(anchor.get_text(" ", strip=True))
                if href and names_match(reporter_name, text):
                    return href if href.startswith("http") else urljoin(fetch_result.final_url, href)
        return None

    def _parse_reporter_page(self, source_page: str, soup) -> list[ReporterPageItem]:
        items: list[ReporterPageItem] = []
        for selector in NAVER_SELECTORS.reporter_page_items:
            for anchor in soup.select(selector):
                item = self._build_item_from_anchor(anchor, source_page)
                if item is not None:
                    items.append(item)
            if items:
                break
        return items

    def _build_item_from_anchor(self, anchor: Tag, source_page: str) -> ReporterPageItem | None:
        href = anchor.get("href")
        if not href or "/article/" not in href:
            return None
        resolved_url = href if href.startswith("http") else urljoin(source_page, href)
        title = normalize_whitespace(anchor.get_text(" ", strip=True))
        card = anchor.parent
        card_text = normalize_whitespace(card.get_text(" ", strip=True)) if card else title
        category_node = card.select_one(".category, .press_edit_news_cate, .list_category") if card else None
        category = normalize_whitespace(category_node.get_text(" ", strip=True)) if category_node is not None else None
        return ReporterPageItem(
            url=resolved_url,
            title=title,
            published_date=extract_date(card_text),
            category=category,
            source_page=source_page,
        )

    def _next_page_url(self, current_url: str, soup, page_number: int) -> str | None:
        for selector in NAVER_SELECTORS.pagination_links:
            for anchor in soup.select(selector):
                href = anchor.get("href")
                text = normalize_whitespace(anchor.get_text(" ", strip=True))
                if href and ("다음" in text or "next" in text.lower() or "page" in href):
                    return href if href.startswith("http") else urljoin(current_url, href)
        parsed = urlparse(current_url)
        query = parse_qs(parsed.query)
        query["page"] = [str(page_number + 1)]
        if "page=" in parsed.query or "journalist" in parsed.path or "reporter" in parsed.path:
            return urlunparse(parsed._replace(query=urlencode({key: values[0] for key, values in query.items()})))
        return None
