"""Naver article parsing and verification."""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from naver_reporter_app.constants import NAVER_SELECTORS, SPECIAL_ARTICLE_LABELS
from naver_reporter_app.schemas import ArticleParseResult
from naver_reporter_app.scrapers.base import HttpFetcher
from naver_reporter_app.utils.text import extract_date, names_match, normalize_office_name, normalize_whitespace, offices_match

BYLINE_NAME_RE = re.compile(r"([가-힣A-Za-z]{2,10})\s*기자")
COMMENT_COUNT_RE = re.compile(r'"commentCount"\s*:\s*([0-9]+)|댓글\s*([0-9,]+)')


class NaverArticleScraper:
    """Fetch and validate article pages."""

    def __init__(self, fetcher: HttpFetcher | None = None) -> None:
        self.fetcher = fetcher or HttpFetcher()

    def parse_article(self, url: str, office_name: str, reporter_name: str) -> ArticleParseResult:
        fetch_result = self.fetcher.get(url)
        soup = fetch_result.soup
        title = self._extract_text(soup, NAVER_SELECTORS.title)
        body = self._extract_text(soup, NAVER_SELECTORS.body)
        published_at_raw = self._extract_text(soup, NAVER_SELECTORS.published_at)
        office = self._extract_office_name(soup)
        actual_reporter_name = self._extract_reporter_name(soup, title=title, body=body)
        reporter_page_url = self._extract_reporter_page_url(soup)
        office_id = self._extract_office_id(fetch_result.final_url, reporter_page_url)
        category = self._extract_category(fetch_result.final_url)
        special_label = self._extract_special_label(title)
        comment_count = self._extract_comment_count(soup, fetch_result.text)

        confidence_score = 0.0
        if names_match(reporter_name, actual_reporter_name):
            confidence_score += 0.5
        if offices_match(office_name, office):
            confidence_score += 0.4
        if reporter_page_url:
            confidence_score += 0.2

        verified = bool(
            title
            and body
            and names_match(reporter_name, actual_reporter_name)
            and offices_match(office_name, office)
            and confidence_score >= 0.9
        )
        return ArticleParseResult(
            url=fetch_result.final_url,
            title=title,
            body=body,
            published_date=extract_date(published_at_raw),
            office_name=office,
            reporter_name=actual_reporter_name,
            reporter_page_url=reporter_page_url,
            category=category,
            office_id=office_id,
            verified=verified,
            confidence_score=round(confidence_score, 2),
            special_label=special_label,
            comment_count=comment_count,
            raw_metadata={
                "published_at_raw": published_at_raw,
                "normalized_office_name": normalize_office_name(office),
                "special_label": special_label,
                "comment_count": comment_count,
            },
        )

    def _extract_text(self, soup: BeautifulSoup, selectors: Iterable[str]) -> str:
        for selector in selectors:
            node = soup.select_one(selector)
            if node is None:
                continue
            if node.name == "meta":
                return normalize_whitespace(node.get("content"))
            text = normalize_whitespace(node.get_text(" ", strip=True))
            if text:
                return text
        return ""

    def _extract_office_name(self, soup: BeautifulSoup) -> str:
        for selector in NAVER_SELECTORS.office_name:
            node = soup.select_one(selector)
            if node is None:
                continue
            if node.name == "meta":
                return normalize_whitespace(node.get("content"))
            if node.name == "img":
                return normalize_whitespace(node.get("alt"))
            text = normalize_whitespace(node.get_text(" ", strip=True))
            if text:
                return text
        return ""

    def _extract_reporter_name(self, soup: BeautifulSoup, *, title: str, body: str) -> str:
        for selector in NAVER_SELECTORS.reporter_name:
            node = soup.select_one(selector)
            if node is None:
                continue
            candidate = node.get("content") if node.name == "meta" else node.get_text(" ", strip=True)
            match = BYLINE_NAME_RE.search(normalize_whitespace(candidate))
            if match:
                return match.group(1)
            clean = normalize_whitespace(candidate).replace("기자", "").strip()
            if clean:
                return clean
        byline_source = f"{title} {body[:180]}"
        match = BYLINE_NAME_RE.search(byline_source)
        return match.group(1) if match else ""

    def _extract_reporter_page_url(self, soup: BeautifulSoup) -> str | None:
        for selector in NAVER_SELECTORS.reporter_link:
            node = soup.select_one(selector)
            if node is None:
                continue
            href = node.get("href")
            if href and ("journalist" in href or "reporter" in href):
                return href if href.startswith("http") else f"https://media.naver.com{href}"
        return None

    def _extract_office_id(self, article_url: str, reporter_url: str | None) -> str | None:
        for candidate in filter(None, [article_url, reporter_url]):
            parsed = urlparse(candidate)
            query = parse_qs(parsed.query)
            if "officeId" in query:
                return query["officeId"][0]
            parts = [part for part in parsed.path.split("/") if part]
            if "article" in parts:
                idx = parts.index("article")
                if len(parts) > idx + 1:
                    return parts[idx + 1]
        return None

    def _extract_category(self, url: str) -> str | None:
        parts = [part for part in urlparse(url).path.split("/") if part]
        return "news" if "article" in parts else None

    def _extract_special_label(self, title: str) -> str | None:
        normalized_title = normalize_whitespace(title)
        for label in SPECIAL_ARTICLE_LABELS:
            if label in normalized_title:
                return label
        return None

    def _extract_comment_count(self, soup: BeautifulSoup, html_text: str) -> int | None:
        selectors = (
            "a.media_end_head_cmtcount_button",
            ".media_end_head_cmtcount_text",
            ".u_cbox_count",
            "[data-comment-count]",
        )
        for selector in selectors:
            node = soup.select_one(selector)
            if node is None:
                continue
            direct = node.get("data-comment-count")
            if direct and direct.isdigit():
                return int(direct)
            digits = re.sub(r"[^0-9]", "", normalize_whitespace(node.get_text(" ", strip=True)))
            if digits:
                return int(digits)
        match = COMMENT_COUNT_RE.search(html_text)
        if not match:
            return None
        raw_value = (match.group(1) or match.group(2) or "").replace(",", "")
        return int(raw_value) if raw_value.isdigit() else None
