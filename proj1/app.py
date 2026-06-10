import json
import os
import re
import threading
import time
import traceback
import uuid
from calendar import monthrange
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Blueprint, Flask, jsonify, redirect, render_template, request, url_for
from openai import OpenAI
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
PROMPT_PATH = os.path.join(BASE_DIR, "prompt.md")

# 통합 실행, 단독 실행, WSGI import 모두 pr/.env 값만 사용한다.
load_dotenv(os.path.join(ROOT_DIR, ".env"), override=True)

bp = Blueprint(
    "proj1",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)

jobs: dict[str, dict[str, Any]] = {}
jobs_lock = threading.Lock()

POSCO_KEYWORDS = [
    "포스코",
    "POSCO",
    "포항제철",
    "광양제철",
    "포스코홀딩스",
    "포스코퓨처엠",
    "포스코인터내셔널",
    "포스코이앤씨",
    "포스코DX",
]

MIN_LATEST_ARTICLES = int(os.getenv("MIN_LATEST_ARTICLES", "20"))
TARGET_POSCO_ARTICLES = int(os.getenv("TARGET_POSCO_ARTICLES", "5"))
MAX_SCAN_ARTICLES = int(os.getenv("MAX_SCAN_ARTICLES", "150"))
MAX_RESULT_SCROLLS = int(os.getenv("MAX_RESULT_SCROLLS", "15"))
POSCO_LOOKBACK_MONTHS = int(os.getenv("POSCO_LOOKBACK_MONTHS", "1"))
MAX_REQUEST_PAGES = int(os.getenv("MAX_REQUEST_PAGES", "8"))

ARTICLE_SELECTORS = [
    "div#dic_area",
    "div.newsct_article",
    "div#articleBodyContents",
    "article",
]


@dataclass
class Article:
    title: str
    url: str
    naver_url: str = ""
    date: str = ""
    media: str = ""
    summary: str = ""
    content: str = ""
    is_posco: bool = False


def now_label() -> str:
    return datetime.now().strftime("%H:%M:%S")


def set_job(job_id: str, **updates: Any) -> None:
    with jobs_lock:
        job = jobs.setdefault(job_id, {})
        job.update(updates)
        job["updated_at"] = time.time()


def get_job(job_id: str) -> dict[str, Any] | None:
    with jobs_lock:
        job = jobs.get(job_id)
        return dict(job) if job else None


def load_office_codes() -> dict[str, str]:
    """Read the office list from prompt.md so the large mapping has a single source."""
    fallback = {
        "연합뉴스": "1001",
        "뉴시스": "1003",
        "머니투데이": "1008",
        "매일경제": "1009",
        "서울경제": "1011",
        "파이낸셜뉴스": "1014",
        "한국경제": "1015",
        "헤럴드경제": "1016",
        "이데일리": "1018",
        "중앙일보": "1025",
        "조선비즈": "1366",
        "뉴스1": "1421",
        "아시아경제": "1277",
        "비즈니스포스트": "2374",
    }
    if not os.path.exists(PROMPT_PATH):
        return fallback

    text = open(PROMPT_PATH, encoding="utf-8").read()
    matches = re.findall(r"([^,\n()]+)\((\d{4})\)", text)
    codes: dict[str, str] = {}
    for raw_name, code in matches:
        name = raw_name.strip()
        if not name or len(name) > 40:
            continue
        # Skip accidental captures from explanatory prose.
        if any(token in name for token in ["http", "URL", "키값", "선택시"]):
            continue
        codes[name] = code

    return {**fallback, **codes}


OFFICE_CODES = load_office_codes()


@bp.app_template_filter("display_date")
def display_date(value: str) -> str:
    value = normalize_text(value)
    if not value:
        return "날짜 미확인"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%Y.%m.%d %H:%M")
    except ValueError:
        return value


@bp.app_template_filter("clean_card_title")
def clean_card_title(value: str) -> str:
    return re.sub(r"^\s*\[[^\]]+\]\s*", "", clean_generated_text(value))


@bp.app_template_filter("clean_reason")
def clean_reason(value: str) -> str:
    text = clean_generated_text(value)
    text = re.sub(r"^기자님의?\s*", "", text)
    text = re.sub(r"^기자의\s*", "", text)
    return text


@bp.app_template_filter("clean_generated")
def clean_generated(value: str) -> str:
    return clean_generated_text(value)


def subtract_months(value: datetime, months: int) -> datetime:
    month = value.month - months
    year = value.year
    while month <= 0:
        month += 12
        year -= 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def parse_article_datetime(value: str, base: datetime | None = None) -> datetime | None:
    value = normalize_text(value)
    if not value:
        return None
    base = base or datetime.now()

    relative = re.search(r"(\d+)\s*(분|시간|일|주|개월)\s*전", value)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        if unit == "분":
            return base - timedelta(minutes=amount)
        if unit == "시간":
            return base - timedelta(hours=amount)
        if unit == "일":
            return base - timedelta(days=amount)
        if unit == "주":
            return base - timedelta(weeks=amount)
        if unit == "개월":
            return subtract_months(base, amount)

    candidates = [
        value.replace("Z", "+00:00"),
        re.sub(r"\.\s*$", "", value).replace(".", "-"),
    ]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed
        except ValueError:
            pass

    match = re.search(r"(\d{4})[.\-](\d{1,2})[.\-](\d{1,2})(?:\.?\s*(\d{1,2}):(\d{2}))?", value)
    if match:
        year, month, day = (int(match.group(i)) for i in range(1, 4))
        hour = int(match.group(4) or 0)
        minute = int(match.group(5) or 0)
        try:
            return datetime(year, month, day, hour, minute)
        except ValueError:
            return None
    return None


def is_recent_article_date(value: str, months: int = 2, base: datetime | None = None) -> bool:
    base = base or datetime.now()
    parsed = parse_article_datetime(value, base)
    if not parsed:
        return False
    cutoff = subtract_months(base, months).replace(hour=0, minute=0, second=0, microsecond=0)
    return parsed >= cutoff


def is_older_than_article_window(value: str, months: int = POSCO_LOOKBACK_MONTHS) -> bool:
    base = datetime.now()
    parsed = parse_article_datetime(value, base)
    if not parsed:
        return False
    cutoff = subtract_months(base, months).replace(hour=0, minute=0, second=0, microsecond=0)
    return parsed < cutoff


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def clean_generated_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\s*\(\[[^\]]+\]\(https?://[^)]+\)\)", "", text)
    text = re.sub(r"\s*\[[^\]]+\]\(https?://[^)]+\)", "", text)
    text = re.sub(r"\s*\(https?://[^)\s]+\)", "", text)
    text = re.sub(r"https?://\S+", "", text)
    return normalize_text(text)


def find_office_code(media_name: str) -> tuple[str | None, str | None]:
    cleaned = normalize_text(media_name)
    if cleaned in OFFICE_CODES:
        return cleaned, OFFICE_CODES[cleaned]

    lowered = cleaned.lower()
    for name, code in OFFICE_CODES.items():
        if name.lower() == lowered:
            return name, code
    for name, code in OFFICE_CODES.items():
        if lowered and (lowered in name.lower() or name.lower() in lowered):
            return name, code
    return None, None


def build_office_search_url(office_code: str) -> str:
    return (
        "https://search.naver.com/search.naver?"
        "ssc=tab.news.all&where=news&sm=tab_opt&sort=1&photo=0&field=0&pd=-1"
        "&query=&mynews=1&office_type=2&office_section_code=3"
        f"&news_office_checked={office_code}&nso=&is_sug_officeid=0"
        "&office_category=0&service_area=0"
    )


def build_reporter_search_url(office_code: str, reporter_name: str) -> str:
    return (
        "https://search.naver.com/search.naver?"
        "ssc=tab.news.all&where=news&sm=tab_opt&sort=1&photo=0&field=2&pd=-1"
        f"&query={quote_plus(reporter_name)}&mynews=1&office_type=2&office_section_code=3"
        f"&news_office_checked={office_code}&nso=&is_sug_officeid=0"
        "&office_category=0&service_area=0"
    )


def build_media_keyword_search_url(office_code: str, keyword: str) -> str:
    return (
        "https://search.naver.com/search.naver?"
        "ssc=tab.news.all&where=news&sm=tab_opt&sort=1&photo=0&field=0&pd=-1"
        f"&query={quote_plus(keyword)}&mynews=1&office_type=2&office_section_code=3"
        f"&news_office_checked={office_code}&nso=&is_sug_officeid=0"
        "&office_category=0&service_area=0"
    )


def is_transient_naver_navigation_error(exc: Exception) -> bool:
    message = str(exc)
    transient_markers = [
        "ERR_NAME_NOT_RESOLVED",
        "ERR_CONNECTION_RESET",
        "ERR_CONNECTION_CLOSED",
        "ERR_CONNECTION_TIMED_OUT",
        "ERR_TIMED_OUT",
        "net::ERR",
    ]
    return "search.naver.com" in message and any(marker in message for marker in transient_markers)


def warm_naver_dns() -> None:
    try:
        requests.get("https://search.naver.com", timeout=5)
    except Exception:
        pass


def goto_naver_with_retries(page, url: str, progress, start_percent: int = 8) -> None:
    attempts = max(1, int(os.getenv("NAVER_GOTO_RETRIES", "4")))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(1200)
            return
        except PlaywrightTimeoutError:
            progress(15, "검색 페이지 응답이 늦어 현재 로드된 내용으로 계속 진행합니다.")
            return
        except Exception as exc:
            last_error = exc
            if not is_transient_naver_navigation_error(exc) or attempt == attempts:
                break
            progress(
                min(15, start_percent + attempt),
                f"네이버 검색 페이지 연결이 불안정해 재시도 중입니다. ({attempt}/{attempts})",
            )
            warm_naver_dns()
            page.wait_for_timeout(900 * attempt)

    raise RuntimeError(
        "네이버 검색 페이지 연결이 불안정해 브라우저 방식 진입에 실패했습니다."
    ) from last_error


def apply_reporter_option(page, reporter_name: str, progress) -> None:
    progress(12, "네이버 옵션을 열어 기자명 필터를 적용 중입니다.")

    # 네이버 옵션 패널은 페이지 구조 변경이 잦아, 먼저 실제 옵션 버튼 클릭을 시도하고
    # 이후 네이버가 페이지에 제공하는 기자명 적용 함수를 호출한다.
    option_candidates = [
        "a:has-text('옵션')",
        "button:has-text('옵션')",
        "#snb .btn_option",
        ".btn_option",
    ]
    for selector in option_candidates:
        try:
            locator = page.locator(selector)
            if locator.count() and locator.first.is_visible():
                locator.first.click(timeout=2500)
                page.wait_for_timeout(500)
                break
        except Exception:
            continue

    page.wait_for_selector("#news_input_reporter_name", state="attached", timeout=8000)
    page.evaluate(
        """
        (reporterName) => {
            const input = document.getElementById("news_input_reporter_name");
            if (!input) throw new Error("기자명 입력란을 찾지 못했습니다.");
            input.value = reporterName;
            input.dispatchEvent(new Event("input", { bubbles: true }));
            input.dispatchEvent(new Event("change", { bubbles: true }));
        }
        """,
        reporter_name,
    )

    before_url = page.url
    try:
        page.evaluate("() => news_submit_reporter_option()")
    except Exception:
        page.evaluate(
            """
            (reporterName) => {
                const form = document.getElementById("news_form");
                if (!form) throw new Error("네이버 뉴스 검색 폼을 찾지 못했습니다.");
                form.field.value = 2;
                form.query.value = reporterName;
                form.submit();
            }
            """,
            reporter_name,
        )

    try:
        page.wait_for_url(lambda current_url: current_url != before_url, timeout=12000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_load_state("domcontentloaded", timeout=25000)
    page.wait_for_timeout(1200)

    if "field=2" not in page.url:
        raise RuntimeError("기자명 옵션 적용에 실패했습니다. 네이버 옵션 UI 구조를 확인해 주세요.")


def article_sort_key(article: Article) -> str:
    return article.date or ""


def pick_article_url(anchor_href: str) -> str:
    if not anchor_href:
        return ""
    return anchor_href.split("?")[0] if "news.naver.com" in anchor_href else anchor_href


def find_naver_article_url(container) -> str:
    if not container:
        return ""
    for anchor in container.select('a[href*="n.news.naver.com/mnews/article/"], a[href*="news.naver.com/mnews/article/"]'):
        href = anchor.get("href", "")
        if href:
            return href
    return ""


def extract_date_from_text(text: str) -> str:
    text = normalize_text(text)
    patterns = [
        r"\d{4}\.\d{2}\.\d{2}\.?\s*\d{1,2}:\d{2}",
        r"\d{4}\.\d{2}\.\d{2}\.?",
        r"\d{4}-\d{2}-\d{2}\s*\d{1,2}:\d{2}",
        r"\d{4}-\d{2}-\d{2}",
        r"\d+분 전",
        r"\d+시간 전",
        r"\d+일 전",
        r"\d+주 전",
        r"\d+개월 전",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return normalize_text(match.group(0))
    return ""


def extract_published_date(soup: BeautifulSoup) -> str:
    meta_selectors = [
        ('meta[property="article:published_time"]', "content"),
        ('meta[name="article:published_time"]', "content"),
        ('meta[property="og:article:published_time"]', "content"),
        ('meta[name="pubdate"]', "content"),
        ('meta[name="publish-date"]', "content"),
        ('meta[name="date"]', "content"),
        ('meta[itemprop="datePublished"]', "content"),
    ]
    for selector, attr in meta_selectors:
        node = soup.select_one(selector)
        if node and node.get(attr):
            return normalize_text(node.get(attr, ""))

    visible_selectors = [
        "span.media_end_head_info_datestamp_time",
        "span._ARTICLE_DATE_TIME",
        "time",
        ".date",
        ".article_date",
        ".viewDate",
        ".view_date",
        ".news_date",
        ".write_date",
        ".byline",
    ]
    for selector in visible_selectors:
        node = soup.select_one(selector)
        if not node:
            continue
        value = normalize_text(
            node.get("data-date-time")
            or node.get("datetime")
            or node.get("content")
            or node.get_text(" ", strip=True)
        )
        extracted = extract_date_from_text(value) or value
        if extracted:
            return extracted
    return ""


def is_probable_article_url(url: str) -> bool:
    if not url.startswith("http"):
        return False
    parsed = urlparse(url)
    blocked_hosts = {
        "search.naver.com",
        "media.naver.com",
        "www.naver.com",
        "naver.com",
        "keep.naver.com",
    }
    if parsed.netloc in blocked_hosts:
        return False
    if "channelPromotion" in url:
        return False
    if "news.naver.com" in parsed.netloc:
        return "/mnews/article/" in parsed.path or "/article/" in parsed.path
    if parsed.scheme not in {"http", "https"} or "." not in parsed.netloc:
        return False
    return True


def is_result_title_anchor(anchor) -> bool:
    title = normalize_text(anchor.get("title") or anchor.get_text(" ", strip=True))
    if not title or title in {"네이버뉴스", "뉴스", "언론사 선정"}:
        return False
    if title.startswith("언론사 선정 언론사가 선정한"):
        return False
    if len(title) < 6:
        return False

    classes = set(anchor.get("class") or [])
    if "news_tit" in classes:
        return True

    href = anchor.get("href", "")
    if (
        href
        and is_probable_article_url(href)
        and any(class_name.startswith("fender-ui_") for class_name in classes)
    ):
        return True

    # Naver's current news card uses generated class names, but the title link
    # consistently carries this text class. Summary/image/menu links do not.
    if "ZndmRRvmX99p7vSVdwfb" in classes:
        return True

    if "n.news.naver.com/mnews/article/" in href or "news.naver.com/mnews/article/" in href:
        return True

    container = anchor.find_parent(["li", "div"])
    container_text = normalize_text(container.get_text(" ", strip=True)) if container else ""
    has_news_card_signal = "네이버뉴스" in container_text or "언론사 선정" in container_text
    has_summary_sibling = bool(container and container.select_one("a.C_1BhQhHmSg2jyIC5psm"))
    return has_news_card_signal and has_summary_sibling


def extract_articles_from_html(html: str, reporter_name: str, media_name: str) -> list[Article]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[Article] = []
    seen: set[str] = set()

    anchors = soup.select("a.news_tit, a.ZndmRRvmX99p7vSVdwfb, a[href]")
    for anchor in anchors:
        if is_result_title_anchor(anchor):
            href = pick_article_url(anchor.get("href", ""))
            title = normalize_text(anchor.get("title") or anchor.get_text(" ", strip=True))
            if not href or not title or href in seen:
                continue
            if not is_probable_article_url(href):
                continue

            container = anchor.find_parent(["li", "div"])
            container_text = normalize_text(container.get_text(" ", strip=True)) if container else title
            naver_url = find_naver_article_url(container)
            date = extract_date_from_text(container_text)
            summary = container_text.replace(title, "").strip()
            candidates.append(
                Article(
                    title=title,
                    url=href,
                    naver_url=naver_url,
                    date=date,
                    media=media_name,
                    summary=summary[:300],
                    is_posco=contains_posco(title),
                )
            )
            seen.add(href)

    return candidates


def contains_posco(text: str) -> bool:
    lowered = (text or "").lower()
    return any(keyword.lower() in lowered for keyword in POSCO_KEYWORDS)


def has_repeated_posco_keyword(text: str, minimum: int = 2) -> bool:
    lowered = (text or "").lower()
    return any(lowered.count(keyword.lower()) >= minimum for keyword in POSCO_KEYWORDS)


def is_posco_article(article: Article) -> bool:
    if contains_posco(article.title):
        return True
    return has_repeated_posco_keyword(article.summary)


def unique_articles(articles: list[Article]) -> list[Article]:
    seen: set[str] = set()
    unique: list[Article] = []
    for article in articles:
        key = article.url or article.title
        if key in seen:
            continue
        seen.add(key)
        unique.append(article)
    return unique


def posco_recent_candidate_count(articles: list[Article]) -> int:
    return sum(
        1
        for article in articles
        if is_posco_article(article)
        and is_recent_article_date(article.date, months=POSCO_LOOKBACK_MONTHS)
    )


def has_crossed_posco_scan_window(articles: list[Article]) -> bool:
    return any(is_older_than_article_window(article.date) for article in articles)


def choose_detail_targets(latest: list[Article], scanned: list[Article]) -> list[Article]:
    targets: list[Article] = []
    for article in latest:
        targets.append(article)
    for article in scanned:
        if contains_posco(article.title) or has_repeated_posco_keyword(article.summary):
            targets.append(article)
    return unique_articles(targets)


def clean_article_body(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    junk_patterns = [
        r"구독.*?추천",
        r"무단전재.*?금지",
        r"Copyright.*",
        r"기자\s*페이지",
    ]
    for pattern in junk_patterns:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    return normalize_text(text)[:8000]


def fetch_article_body(page, url: str) -> tuple[str, str]:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=18000)
        page.wait_for_timeout(600)
        html = page.content()
    except Exception:
        return "", ""

    soup = BeautifulSoup(html, "html.parser")
    date = extract_published_date(soup)

    for selector in ARTICLE_SELECTORS:
        node = soup.select_one(selector)
        if node:
            body = clean_article_body(node.get_text(" ", strip=True))
            if body:
                return body, date

    paragraphs = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
    return clean_article_body(paragraphs), date


def fetch_article_body_requests(session: requests.Session, url: str) -> tuple[str, str]:
    try:
        response = session.get(url, timeout=int(os.getenv("REQUEST_TIMEOUT", "12")))
        response.raise_for_status()
    except Exception:
        return "", ""

    soup = BeautifulSoup(response.text, "html.parser")
    date = extract_published_date(soup)

    for selector in ARTICLE_SELECTORS:
        node = soup.select_one(selector)
        if node:
            body = clean_article_body(node.get_text(" ", strip=True))
            if body:
                return body, date

    paragraphs = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
    return clean_article_body(paragraphs), date


def fetch_naver_article_date(page, url: str) -> str:
    if not url:
        return ""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=12000)
        page.wait_for_timeout(400)
        soup = BeautifulSoup(page.content(), "html.parser")
        return extract_published_date(soup)
    except Exception:
        return ""


def fetch_naver_article_date_requests(session: requests.Session, url: str) -> str:
    if not url:
        return ""
    try:
        response = session.get(url, timeout=int(os.getenv("REQUEST_TIMEOUT", "12")))
        response.raise_for_status()
        return extract_published_date(BeautifulSoup(response.text, "html.parser"))
    except Exception:
        return ""


def crawl_naver_news_requests(
    media_name: str,
    reporter_name: str,
    matched_media: str,
    office_code: str,
    url: str,
    progress,
    allow_keyword_fallback: bool = True,
) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        }
    )

    seen: set[str] = set()
    articles: list[Article] = []
    max_articles = max(int(os.getenv("MAX_ARTICLES", "20")), MIN_LATEST_ARTICLES)

    for page_idx in range(MAX_REQUEST_PAGES):
        start = page_idx * 10 + 1
        page_url = f"{url}&start={start}" if page_idx else url
        progress(
            min(40, 15 + page_idx * 4),
            f"최신기사 20건 수집 후 최근 1개월 포스코 기사 후보를 확인 중입니다. ({page_idx + 1}/{MAX_REQUEST_PAGES})",
        )
        response = session.get(page_url, timeout=int(os.getenv("REQUEST_TIMEOUT", "12")))
        if response.status_code in {403, 429} and articles:
            break
        response.raise_for_status()
        page_articles: list[Article] = []
        for article in extract_articles_from_html(response.text, reporter_name, matched_media or media_name):
            if article.url not in seen:
                seen.add(article.url)
                articles.append(article)
                page_articles.append(article)
        if len(articles) >= max_articles and posco_recent_candidate_count(articles) >= TARGET_POSCO_ARTICLES:
            break
        if len(articles) >= max_articles and has_crossed_posco_scan_window(page_articles):
            break

    if not articles:
        if allow_keyword_fallback and "field=2" in url:
            progress(40, "기자명 옵션 결과가 없어 같은 언론사 내 이름 검색으로 보완 수집합니다.")
            return crawl_naver_news_requests(
                media_name,
                reporter_name,
                matched_media,
                office_code,
                build_media_keyword_search_url(office_code, reporter_name),
                progress,
                allow_keyword_fallback=False,
            )
        raise RuntimeError("검색 결과에서 기사를 찾지 못했습니다. 언론사명과 기자명을 확인해 주세요.")

    scanned = articles[:MAX_SCAN_ARTICLES]
    latest = scanned[:max_articles]
    detail_targets = choose_detail_targets(latest, scanned)

    total = max(len(detail_targets), 1)
    for idx, article in enumerate(detail_targets, start=1):
        progress(42 + int(idx / total * 22), f"기사 원문을 요청 방식으로 수집 중입니다. ({idx}/{total})")
        content, date = fetch_article_body_requests(session, article.url)
        if not date and article.naver_url:
            date = fetch_naver_article_date_requests(session, article.naver_url)
        article.content = content
        if date and not article.date:
            article.date = date
        article.is_posco = is_posco_article(article)

    posco_articles = [
        article
        for article in scanned
        if article.is_posco and is_recent_article_date(article.date, months=POSCO_LOOKBACK_MONTHS)
    ][:TARGET_POSCO_ARTICLES]
    return {
        "media_name": matched_media or media_name,
        "office_code": office_code,
        "reporter_name": reporter_name,
        "search_url": url,
        "latest_articles": [asdict(article) for article in latest],
        "posco_articles": [asdict(article) for article in posco_articles[:TARGET_POSCO_ARTICLES]],
    }


def crawl_naver_news(media_name: str, reporter_name: str, progress) -> dict[str, Any]:
    matched_media, office_code = find_office_code(media_name)
    if not office_code:
        supported = ", ".join(list(OFFICE_CODES.keys())[:80])
        raise ValueError(f"지원하지 않는 언론사입니다. 지원 언론사 예시: {supported}")

    progress(8, f"{matched_media}({office_code}) 언론사 필터가 적용된 네이버 뉴스 페이지를 여는 중입니다.")
    url = build_office_search_url(office_code)
    headless = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() != "false"
    viewport = {
        "width": int(os.getenv("PLAYWRIGHT_VIEWPORT_WIDTH", "1280")),
        "height": int(os.getenv("PLAYWRIGHT_VIEWPORT_HEIGHT", "800")),
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                locale=os.getenv("PLAYWRIGHT_LOCALE", "ko-KR"),
                viewport=viewport,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                ),
            )
            page = context.new_page()

            try:
                goto_naver_with_retries(page, url, progress)
            except RuntimeError as exc:
                if not is_transient_naver_navigation_error(exc.__cause__ or exc):
                    raise
                browser.close()
                progress(18, "브라우저 연결이 불안정해 요청 방식으로 같은 조건의 검색 결과를 수집합니다.")
                fallback_url = build_reporter_search_url(office_code, reporter_name)
                return crawl_naver_news_requests(
                    media_name,
                    reporter_name,
                    matched_media or media_name,
                    office_code,
                    fallback_url,
                    progress,
                )

            apply_reporter_option(page, reporter_name, progress)
            url = page.url

            articles: list[Article] = []
            last_count = 0
            stable_rounds = 0
            max_articles = max(int(os.getenv("MAX_ARTICLES", "20")), MIN_LATEST_ARTICLES)
            for idx in range(MAX_RESULT_SCROLLS):
                articles = unique_articles(extract_articles_from_html(page.content(), reporter_name, matched_media or media_name))
                enough_latest = len(articles) >= max_articles
                enough_posco = posco_recent_candidate_count(articles) >= TARGET_POSCO_ARTICLES
                crossed_posco_window = has_crossed_posco_scan_window(articles)
                if enough_latest and (enough_posco or crossed_posco_window):
                    break
                if len(articles) == last_count:
                    stable_rounds += 1
                else:
                    stable_rounds = 0
                if stable_rounds >= 6 and len(articles) >= MIN_LATEST_ARTICLES:
                    break
                progress(
                    min(40, 15 + idx),
                    f"최신기사 20건 수집 후 최근 1개월 포스코 기사 후보를 확인 중입니다. ({idx + 1}/{MAX_RESULT_SCROLLS}, 기사 {len(articles)}건)",
                )
                page.mouse.wheel(0, 1800)
                page.wait_for_timeout(900)
                last_count = len(articles)

            articles = unique_articles(extract_articles_from_html(page.content(), reporter_name, matched_media or media_name))
            if not articles:
                browser.close()
                progress(40, "기자명 옵션 결과가 없어 같은 언론사 내 이름 검색으로 보완 수집합니다.")
                fallback_url = build_media_keyword_search_url(office_code, reporter_name)
                return crawl_naver_news_requests(
                    media_name,
                    reporter_name,
                    matched_media or media_name,
                    office_code,
                    fallback_url,
                    progress,
                )

            scanned = articles[:MAX_SCAN_ARTICLES]
            latest = scanned[:max_articles]
            detail_targets = choose_detail_targets(latest, scanned)

            detail_page = context.new_page()
            total = max(len(detail_targets), 1)
            for idx, article in enumerate(detail_targets, start=1):
                progress(42 + int(idx / total * 22), f"기사 원문을 수집 중입니다. ({idx}/{total})")
                content, date = fetch_article_body(detail_page, article.url)
                if not date and article.naver_url:
                    date = fetch_naver_article_date(detail_page, article.naver_url)
                article.content = content
                if date and not article.date:
                    article.date = date
                article.is_posco = is_posco_article(article)

            browser.close()
            posco_articles = [
                article
                for article in scanned
                if article.is_posco and is_recent_article_date(article.date, months=POSCO_LOOKBACK_MONTHS)
            ][:TARGET_POSCO_ARTICLES]
    except Exception as exc:
        with open(os.path.join(BASE_DIR, "last_crawler_error.log"), "w", encoding="utf-8") as log_file:
            log_file.write(f"{type(exc).__name__}: {exc}\n")
            log_file.write(traceback.format_exc())
        if "WinError 5" in str(exc) or "Access is denied" in str(exc):
            raise RuntimeError("네이버 옵션 UI 조작을 위해 브라우저 실행이 필요하지만 권한 오류로 실행하지 못했습니다.") from exc
        raise

    return {
        "media_name": matched_media or media_name,
        "office_code": office_code,
        "reporter_name": reporter_name,
        "search_url": url,
        "latest_articles": [asdict(article) for article in latest],
        "posco_articles": [asdict(article) for article in posco_articles[:TARGET_POSCO_ARTICLES]],
    }


def article_brief(articles: list[dict[str, Any]]) -> str:
    lines = []
    for idx, article in enumerate(articles, start=1):
        content = article.get("content") or article.get("summary") or "본문 미수집"
        lines.append(
            f"[{idx}] 제목: {article.get('title', '')}\n"
            f"날짜: {article.get('date', '')}\n"
            f"URL: {article.get('url', '')}\n"
            f"본문/요약: {content[:1400]}"
        )
    return "\n\n".join(lines)


def safe_json_loads(text: str, fallback: dict[str, Any]) -> dict[str, Any]:
    if not text:
        return fallback
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    if start >= 0:
        try:
            parsed, _ = json.JSONDecoder().raw_decode(cleaned[start:])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            cleaned = match.group(0)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        fallback["raw"] = text
        return fallback


def extract_openai_text(response: Any) -> str:
    text = getattr(response, "output_text", "") or ""
    if text:
        return text

    if not hasattr(response, "model_dump"):
        return ""

    chunks: list[str] = []
    for item in response.model_dump().get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            content_text = content.get("text")
            if content_text:
                chunks.append(content_text)
    return "".join(chunks)


def extract_openai_web_search_metadata(response: Any) -> dict[str, Any]:
    if not hasattr(response, "model_dump"):
        return {}

    dumped = response.model_dump()
    searches: list[dict[str, Any]] = []
    citations: list[dict[str, str]] = []
    seen_citations: set[tuple[str, str]] = set()

    for item in dumped.get("output", []):
        if item.get("type") in {"web_search_call", "web_search_preview"}:
            searches.append({k: v for k, v in item.items() if k != "id"})
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            for annotation in content.get("annotations", []) or []:
                url = annotation.get("url")
                title = annotation.get("title") or url
                if not url:
                    continue
                key = (title, url)
                if key in seen_citations:
                    continue
                seen_citations.add(key)
                citations.append({"title": title, "url": url})

    metadata: dict[str, Any] = {}
    if searches:
        metadata["searches"] = searches
    if citations:
        metadata["citations"] = citations
    return metadata


def call_openai_json(
    system_prompt: str,
    user_prompt: str,
    *,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | None = None,
    model_env: str = "OPENAI_MODEL",
    fallback_model_env: str = "OPENAI_FALLBACK_MODEL",
) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(".env에 OPENAI_API_KEY가 없습니다.")

    client = OpenAI(api_key=api_key)
    model = os.getenv(model_env) or os.getenv("OPENAI_MODEL", "gpt-5.5")
    fallback_model = (
        os.getenv(fallback_model_env)
        or os.getenv("OPENAI_FALLBACK_MODEL")
        or "gpt-4o-mini"
    )

    def request_with_model(model_name: str):
        payload: dict[str, Any] = {
            "model": model_name,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        return client.responses.create(**payload)

    try:
        response = request_with_model(model)
    except Exception:
        if not fallback_model or fallback_model == model:
            raise
        response = request_with_model(fallback_model)

    text = extract_openai_text(response)
    parsed = safe_json_loads(text, {"raw": text})
    metadata = extract_openai_web_search_metadata(response)
    if metadata:
        parsed["_web_search"] = metadata
    return parsed


def call_openai_web_search_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    web_search_tool = os.getenv("OPENAI_WEB_SEARCH_TOOL", "").strip() or "web_search"
    tool_choice = os.getenv("OPENAI_WEB_SEARCH_TOOL_CHOICE", "").strip() or "required"
    search_context_size = os.getenv("OPENAI_WEB_SEARCH_CONTEXT_SIZE", "").strip()
    tool: dict[str, Any] = {"type": web_search_tool}
    if search_context_size:
        tool["search_context_size"] = search_context_size

    return call_openai_json(
        system_prompt,
        user_prompt,
        tools=[tool],
        tool_choice=tool_choice,
        model_env="OPENAI_WEB_SEARCH_MODEL",
        fallback_model_env="OPENAI_WEB_SEARCH_FALLBACK_MODEL",
    )


def find_nested_value(data: Any, keys: set[str]) -> Any:
    if isinstance(data, dict):
        for key, value in data.items():
            if key in keys:
                return value
        for value in data.values():
            found = find_nested_value(value, keys)
            if found:
                return found
    if isinstance(data, list):
        for item in data:
            found = find_nested_value(item, keys)
            if found:
                return found
    return None


def normalize_talking_analysis(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"meeting_strategy": "", "talking_points": [], "raw": str(data)}

    normalized = dict(data)
    strategy = (
        data.get("meeting_strategy")
        or data.get("strategy")
        or data.get("overview")
        or data.get("summary")
        or find_nested_value(data, {"meeting_strategy", "strategy", "overview", "summary"})
        or ""
    )
    normalized["meeting_strategy"] = clean_generated_text(strategy)

    raw_points = (
        data.get("talking_points")
        or data.get("key_talking_points")
        or data.get("key_points")
        or data.get("points")
        or data.get("talking_point")
        or data.get("talkingPoints")
        or data.get("items")
        or find_nested_value(
            data,
            {"talking_points", "key_talking_points", "key_points", "points", "talking_point", "talkingPoints", "items"},
        )
        or []
    )
    if isinstance(raw_points, dict):
        raw_points = [raw_points]
    if not isinstance(raw_points, list):
        raw_points = []

    points: list[dict[str, str]] = []
    for item in raw_points:
        if isinstance(item, str):
            text = clean_generated_text(item)
            if text:
                points.append({"title": "핵심 포인트", "scenario": text, "reason": ""})
            continue
        if not isinstance(item, dict):
            continue
        title = clean_generated_text(item.get("title") or item.get("name") or item.get("headline") or "")
        scenario = clean_generated_text(
            item.get("scenario")
            or item.get("script")
            or item.get("content")
            or item.get("message")
            or item.get("body")
            or item.get("description")
            or ""
        )
        reason = clean_generated_text(item.get("reason") or item.get("rationale") or item.get("why") or "")
        if title or scenario:
            points.append(
                {
                    "title": title or "핵심 포인트",
                    "scenario": scenario,
                    "reason": reason,
                }
            )

    normalized["talking_points"] = points
    if "raw" in normalized:
        normalized["raw"] = clean_generated_text(normalized["raw"])
    return normalized


def analyze_general(
    media_name: str,
    reporter_name: str,
    latest_articles: list[dict[str, Any]],
    posco_articles: list[dict[str, Any]],
) -> dict[str, Any]:
    system_prompt = (
        "너는 한국 기업 홍보 담당자를 돕는 언론 분석가다. "
        "반드시 한국어 JSON만 반환하고, 추측과 근거를 구분해 간결하게 작성한다."
    )
    user_prompt = f"""
언론사: {media_name}
기자: {reporter_name}

아래 최신 기사 목록 약 20건과 최근 1개월 내 포스코그룹 관련 기사 최대 5건을 바탕으로 JSON을 만들어라.
전체 문체 규칙:
- 괄호 설명은 꼭 필요한 고유명사 보충 외에는 쓰지 않는다.
- "점검", "추적", "배치", "연결", "정리"처럼 명사형으로 끝나는 어색한 문장을 피한다.
- 관심 주제와 기사 분석 설명은 자연스러운 설명체로 마무리한다. 예: "다룹니다", "짚고 있습니다", "강조합니다", "이어집니다".
- 문장은 짧게 쓴다. 중복 표현과 추측성 수식어를 줄인다.
관심 주제 규칙:
- 기자가 최근 가장 관심을 둔 큰 주제를 관심도 높은 순서로 정확히 5개 작성한다.
- name은 제목만 읽어도 의미가 이해되도록 12~20글자 내외의 설명형 제목으로 작성한다.
- name은 너무 짧은 단어형 제목을 피하고, 주제와 방향성이 같이 드러나게 쓴다.
- name에는 ① 같은 번호와 괄호를 넣지 않는다.
- evidence는 2문장 이내로 작성한다. 문장 끝은 자연스러운 설명체로 쓴다.
기사 분석 규칙:
- tone.summary는 관찰자 관점의 분석문으로, 기자가 요즘 어떤 생각과 흐름, 키워드를 중심으로 기사를 쓰는지 한눈에 파악되게 작성한다.
- tone.summary는 "나는", "제가", "필자는" 같은 1인칭 표현으로 시작하거나 1인칭 화자로 쓰지 않는다.
- tone.summary는 "최근 기사는", "해당 기자는", "보도 흐름은"처럼 분석 서술체로 시작한다.
- tone.summary는 최신기사 20개와 최근 1개월 내 포스코그룹 관련 기사 최대 5개를 합쳐 2줄 이내 핵심 요약으로 작성한다.
- tone.summary만 봐도 최근 관심 이슈, 기사 결, 보도 시각, 보도 흐름이 파악되어야 한다.
- 기사에서 친기업적, 비판적, 객관적, 규제 중심, 현장 중심, 투자자 관점 등 특정 시각이 드러나면 tone.summary에 자연스럽게 반영한다.
- 특정 주제나 키워드에 대해 기자의 스탠스가 보이면 tone.summary 또는 tone.features에 "해당 주제에 대한 입장"으로 반영한다. 예: 긍정적, 부정적, 비판적, 신중론, 규제 강화, 산업 육성.
- 포스코 관련 내용이 있으면 tone.features 마지막 항목에 반드시 별도로 정리한다. 포스코그룹 계열사나 관련 내용은 "포스코그룹"이라는 표현을 우선 사용한다.
- 포스코그룹 관련 tone.features 항목은 다른 항목보다 조금 더 구체적으로 쓰고, 제조·공급망·투자·에너지·소재 등 어떤 흐름과 연결되는지 밝힌다.
- tone.features는 summary를 조금 더 상세하게 풀어주는 주요내용 3개 내외로 작성한다.
- tone.features에는 기사 제목을 넣지 않는다. 최근 기자가 어떤 주제에 관심 있고 어떤 내용을 주로 다루는지 한눈에 들어오게 쓴다.
- [단독], [기획], [현장취재], [르포], [기자수첩], 연속 보도 등 기자 고유 보도 성격은 tone.features 마지막 항목에서만 간단히 언급한다. 기사 제목은 쓰지 않는다.
- "혼합", "중립적" 같은 논조 라벨이나 stance 표현은 features에 넣지 않는다.
키워드 규칙:
- keywords는 최신 기사 목록 약 20건을 바탕으로 기자의 가장 큰 관심 키워드만 정확히 5개 작성한다.
- keywords는 관심도 높은 순서로 정렬한다. 첫 번째가 가장 관심도가 높은 키워드다.
- keywords는 관심 주제와 구별되도록 짧은 단어 중심으로 작성한다.
- word는 가능하면 2~8글자 내외의 짧은 키워드로 작성한다.
- 가장 핵심인 상위 2개는 frequency "높음", 나머지 3개는 "중간"으로 작성한다.
- frequency "낮음"은 가급적 사용하지 않는다.
스키마:
{{
  "interest_areas": [{{"name": "분야", "evidence": "근거"}}],
  "tone": {{"stance": "비판적|중립적|우호적|혼합", "summary": "전체 요약", "features": ["특징"]}},
  "keywords": [{{"word": "키워드", "frequency": "높음|중간|낮음"}}]
}}

기사:
{article_brief(latest_articles)}

포스코그룹 관련 기사:
{article_brief(posco_articles)}
"""
    return call_openai_json(system_prompt, user_prompt)


def analyze_talking_points(
    media_name: str,
    reporter_name: str,
    latest_articles: list[dict[str, Any]],
    posco_articles: list[dict[str, Any]],
    general_analysis: dict[str, Any],
) -> dict[str, Any]:
    system_prompt = (
        "너는 포스코 홍보 담당자의 미팅 브리핑을 작성하는 PR 전략가다. "
        "제공된 최신 기사 목록으로 기자의 관심사를 파악하고, "
        "OpenAI 웹 검색 도구로 그 관심사와 맞닿는 포스코그룹 최신 공개 이슈를 넓게 확인한다. "
        "반드시 한국어 JSON만 반환하고, 홍보 실무자가 바로 활용할 수 있는 자연스러운 표현을 쓴다."
    )
    user_prompt = f"""
언론사: {media_name}
기자: {reporter_name}

종합 분석과 최신 기사로 기자의 관심사를 먼저 파악한 뒤, OpenAI 웹 검색 도구로 확인한 포스코그룹 최신 공개 정보를 연결해 JSON을 만들어라.
포스코 관련 기사 목록은 참고 자료일 뿐이며, 수집 건수가 0~1건이어도 그 기사 하나에 토킹 포인트 전체를 종속시키지 않는다.
수집된 포스코 관련 기사가 적으면 기자의 관심 주제와 겹치는 포스코그룹 이슈를 웹 검색으로 넓게 찾아 구성한다.
예: 철강, 이차전지 소재, 에너지, 공급망, 통상, 건설/인프라, ESG, 노사, 안전, 투자, 미래소재, 그룹사 이슈 등.
웹 검색 결과를 사용할 때는 게시일과 현재성을 반드시 구분한다.
최정우 회장 시기 문구, "더불어 함께 발전하는 기업시민", "With POSCO"처럼 과거 경영이념·슬로건은 최근 1년 내 공식 자료에서 현재 메시지로 확인되지 않으면 사용하지 않는다.
현재 포스코그룹 메시지는 장인화 회장 체제의 소재 혁신, 철강 본원 경쟁력, 이차전지 소재, 저탄소 전환, 공급망, 글로벌 초일류 기업 도약 등 최신 이슈 중심으로 구성한다.
오래된 자료가 검색되면 역사적 배경으로만 취급하고, scenario와 talking_points의 핵심 근거로 쓰지 않는다.
포스코그룹 관련 이슈를 구성할 때는 가능한 한 사업회사를 구분한다. 예: 포스코, 포스코인터내셔널, 포스코이앤씨, 포스코퓨처엠, 포스코DX.
각 사업회사별 내용은 철강, 에너지·트레이딩, 건설·인프라, 이차전지 소재, 디지털·AI·스마트팩토리처럼 역할과 사업 맥락을 구분해 설명한다.
OpenAI 웹 검색으로 확인 가능한 매출, 투자액, 생산능력, 수주액, 공급량, 감축 목표, 기간, 시장 점유율, 설비 규모 등 수치가 있으면 가능한 많이 반영한다.
수치를 쓸 때는 과장하지 말고 확인 가능한 공개 정보만 사용한다. 불확실하면 숫자를 만들지 않는다.
기자의 최근 기사 제목이나 내용에 "칼럼", "논설", "주필", "데스크", "사설", "시론" 성격이 강하게 나타나면 일반 취재기자가 아니라 데스크·논설형 인물로 간주한다.
데스크·논설형 인물에게는 마이너한 제품 홍보, 지역 행사, 단발성 CSR, 세부 사업 소개보다 포스코그룹 C레벨 경영층이 대담할 수 있는 거시 의제를 우선한다.
이 경우 토킹 포인트는 산업정책, 국가 경쟁력, 공급망 안보, 에너지 전환, 저탄소 철강, 이차전지 소재 생태계, 통상·지정학, 기업 거버넌스, 노사와 사회적 책임처럼 경영층 관점의 의제로 구성한다.
데스크·논설형 인물에게는 "우리 사업을 소개"하는 톤보다, 포스코그룹이 한국 산업과 국가 경제에서 어떤 구조적 역할을 할지 논의하는 톤을 사용한다.

meeting_strategy는 "토킹 포인트 개요"에 들어갈 내용이다.
종합 분석 탭의 관심 주제, 기사 분석, 관심 키워드를 바탕으로 포스코그룹 홍보 직원이 해당 기자를 만났을 때 어떤 방향으로 대화를 가져가면 좋을지 전반적인 개요를 작성한다.
기자 관심사 → 포스코그룹과의 접점 → 대화에서 사용할 기회/리스크 메시지 순서가 자연스럽게 이어져야 한다.
meeting_strategy는 약 3줄로 작성한다. 길어도 4줄을 넘기지 않는다.
OpenAI 웹 검색으로 조사한 기자 관심사와 부합하는 포스코그룹 이슈를 종합적으로 고려해, 어떤 내용으로 대화하면 좋을지 조언하는 형식으로 쓴다.
"하겠습니다", "말씀드리겠습니다" 같은 실행 선언형 대신 "연결하면 효과적이다", "짚는 것이 좋다", "방어 논리를 준비하는 것이 좋다" 같은 조언형 문장으로 쓴다.
장황한 세부 스크립트는 넣지 않는다.
meeting_strategy와 talking_points의 모든 문자열에는 출처 표기, URL, 마크다운 링크를 넣지 않는다.
예: "([v.daum.net](https://...))", "[출처](https://...)", "https://..." 같은 표현은 절대 쓰지 않는다.

talking_points는 중요도 순으로 3~5개 작성한다. 중복되는 내용이 있으면 5개를 억지로 채우지 않는다.
각 포인트는 기자의 관심사와 부합하는 포스코그룹 관련 이슈를 OpenAI 웹 검색으로 보강해 구성한다.
가능하면 서로 다른 접점으로 구성하고, 같은 포스코 기사 1건을 반복 변주하지 않는다.
최신 기사 목록은 기자의 관심사 판단에 쓰고, 포스코 관련 기사 목록은 실제로 기자가 포스코그룹을 다룬 흔적을 확인하는 보조 근거로만 쓴다.
칼럼·논설·주필·데스크형 기자로 판단되면 talking_points의 title과 scenario는 C레벨 경영층 대담용 거시 의제로 작성한다.
이 경우 title은 "국가 산업 경쟁력과 소재 안보", "저탄소 전환과 제조업 생존 전략"처럼 경영 아젠다로 보이게 쓴다.
이 경우 scenario는 단기 홍보성 설명보다 회장·사장단이 말할 수 있는 산업 전망, 정책 방향, 기업의 구조적 역할, 리스크 대응 관점으로 작성한다.
각 title은 짧고 실무적인 제목으로 쓴다. 대괄호 머릿말은 쓰지 않는다.
"피벗 브릿지", "루트 A/B/C", "A)", "B)", "메인 피칭"이라는 표현은 쓰지 않는다.
scenario는 포스코 커뮤니케이션실 15년 경력의 언론 대응 관계자가 기자에게 실제로 말하는 느낌의 1인칭 대화문으로 작성한다.
scenario는 종합분석에서 도출된 기자의 관심사를 바탕으로 대화를 시작하고, OpenAI 웹 검색으로 파악한 포스코그룹 최신 공개 이슈와 수집 기사 정보를 자연스럽게 연결한다.
scenario에는 "기자님", "기자님께서", "기자님의" 같은 표현을 어떤 위치에도 쓰지 않는다.
scenario는 "최근에 쓰신", "관심을 보이신", "주목하고 계신"처럼 직접 호칭을 생략한 문장으로 시작한다.
scenario는 긴 서술형 문단이 아니라 개조식으로 작성한다. 각 항목은 "·" 또는 "-"로 시작하는 3~5개 불릿으로 구성한다.
scenario에는 포스코그룹 전체 관점의 거시 의제와 사업회사별 구체 내용을 함께 넣는다.
scenario에는 가능한 한 숫자, 기간, 규모, 목표, 투자액, 생산능력, 수주액 등 정량 정보를 포함한다.
scenario의 불릿은 "거시 의제 → 사업회사별 연결 → 수치 근거 → 대화 포인트" 흐름으로 구성한다.
scenario는 500자 이내다.
reason은 해당 포인트가 기자 관심사와 어떻게 연결되는지, 또는 포스코그룹 커뮤니케이션에 어떤 효과가 있는지 설명한다.
reason은 "기자님의", "기자의" 같은 반복적 시작 문구 없이 바로 핵심 이유로 시작한다.
스키마:
{{
  "meeting_strategy": "토킹 포인트 개요",
  "talking_points": [
    {{"title": "단계명과 목적", "scenario": "1인칭 토킹 시나리오", "reason": "카드의 역할"}}
  ]
}}

종합 분석:
{json.dumps(general_analysis, ensure_ascii=False)}

최신 기사:
{article_brief(latest_articles)}

포스코 관련 기사:
{article_brief(posco_articles)}
"""
    return normalize_talking_analysis(call_openai_web_search_json(system_prompt, user_prompt))


def run_job(job_id: str, media_name: str, reporter_name: str) -> None:
    def progress(percent: int, message: str) -> None:
        set_job(
            job_id,
            status="running",
            percent=max(0, min(percent, 99)),
            message=message,
            log=get_job(job_id).get("log", []) + [{"time": now_label(), "message": message}],
        )

    try:
        progress(3, "작업을 시작했습니다.")
        crawled = crawl_naver_news(media_name, reporter_name, progress)
        progress(68, "최신 기사 기반 종합 분석을 요청 중입니다.")
        general = analyze_general(
            crawled["media_name"],
            reporter_name,
            crawled["latest_articles"],
            crawled["posco_articles"],
        )
        progress(84, "포스코 기사 기반 토킹 포인트를 생성 중입니다.")
        talking = analyze_talking_points(
            crawled["media_name"],
            reporter_name,
            crawled["latest_articles"],
            crawled["posco_articles"],
            general,
        )
        set_job(
            job_id,
            status="done",
            percent=100,
            message="분석이 완료되었습니다.",
            result={**crawled, "general_analysis": general, "talking_analysis": talking},
            log=get_job(job_id).get("log", []) + [{"time": now_label(), "message": "분석이 완료되었습니다."}],
        )
    except Exception as exc:
        with open(os.path.join(BASE_DIR, "last_job_error.log"), "w", encoding="utf-8") as log_file:
            log_file.write(f"{type(exc).__name__}: {exc}\n")
            log_file.write(traceback.format_exc())
        set_job(
            job_id,
            status="error",
            percent=100,
            message=str(exc),
            error=str(exc),
            traceback=traceback.format_exc(),
        )


@bp.get("/")
def index():
    return render_template(
        "proj1/index.html",
        office_count=len(OFFICE_CODES),
        media_names=sorted(OFFICE_CODES.keys()),
    )


@bp.post("/search")
def search():
    media_name = normalize_text(request.form.get("media_name", ""))
    reporter_name = normalize_text(request.form.get("reporter_name", ""))
    if not media_name or not reporter_name:
        return render_template(
            "proj1/index.html",
            office_count=len(OFFICE_CODES),
            media_names=sorted(OFFICE_CODES.keys()),
            error="언론사명과 기자명을 모두 입력해 주세요.",
        ), 400

    job_id = uuid.uuid4().hex
    set_job(
        job_id,
        status="queued",
        percent=0,
        message="작업 대기 중입니다.",
        media_name=media_name,
        reporter_name=reporter_name,
        log=[{"time": now_label(), "message": "작업 대기 중입니다."}],
    )
    thread = threading.Thread(target=run_job, args=(job_id, media_name, reporter_name), daemon=True)
    thread.start()
    return redirect(url_for("proj1.progress", job_id=job_id))


@bp.get("/progress/<job_id>")
def progress(job_id: str):
    job = get_job(job_id)
    if not job:
        return redirect(url_for("proj1.index"))
    return render_template("proj1/progress.html", job_id=job_id, job=job)


@bp.get("/api/status/<job_id>")
def api_status(job_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify({"status": "missing", "message": "작업을 찾을 수 없습니다."}), 404
    safe_job = {k: v for k, v in job.items() if k != "traceback"}
    if os.getenv("FLASK_DEBUG", "false").lower() == "true" and job.get("traceback"):
        safe_job["traceback"] = job["traceback"]
    if job.get("status") == "done":
        safe_job["result_url"] = url_for("proj1.result", job_id=job_id)
    return jsonify(safe_job)


@bp.get("/result/<job_id>")
def result(job_id: str):
    job = get_job(job_id)
    if not job:
        return redirect(url_for("proj1.index"))
    if job.get("status") != "done":
        return redirect(url_for("proj1.progress", job_id=job_id))
    return render_template("proj1/result.html", job=job, result=job["result"])


def create_standalone_app() -> Flask:
    standalone = Flask(__name__)
    standalone.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-secret")
    standalone.register_blueprint(bp)
    return standalone


if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5001"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    create_standalone_app().run(host=host, port=port, debug=debug, use_reloader=False)
