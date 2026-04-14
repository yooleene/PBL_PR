"""Constants and selectors for Naver parsing."""

from __future__ import annotations

from dataclasses import dataclass

NAVER_NEWS_HOSTS = ("news.naver.com", "n.news.naver.com", "media.naver.com")
NAVER_SEARCH_URL = "https://search.naver.com/search.naver"
NAVER_OPEN_API_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"

DEFAULT_SEARCH_QUERY_TEMPLATES = (
    "{office_name} {reporter_name} 기자",
    "{reporter_name} 기자 {office_name}",
    "{office_name} {reporter_name}",
)

SPECIAL_ARTICLE_LABELS = (
    "단독",
    "기획",
    "르포",
    "기자수첩",
    "논설",
    "사설",
    "오피니언",
)

POSCO_GROUP_KEYWORDS = (
    "포스코",
    "포스코그룹",
    "포스코홀딩스",
    "포스코퓨처엠",
    "포스코인터내셔널",
    "포스코이앤씨",
    "포스코DX",
    "포스코스틸리온",
    "포스코엠텍",
)

POSCO_GROUP_COMPANIES = (
    "포스코홀딩스",
    "포스코",
    "포스코퓨처엠",
    "포스코인터내셔널",
    "포스코이앤씨",
    "포스코DX",
)

KOREAN_STOPWORDS = {
    "기자",
    "뉴스",
    "사진",
    "영상",
    "대한",
    "관련",
    "지난",
    "이번",
    "위해",
    "통해",
    "으로",
    "에서",
    "했다",
    "있다",
    "것",
    "등",
    "및",
    "더",
    "또",
    "오늘",
    "오전",
    "오후",
}


@dataclass(frozen=True)
class SelectorSet:
    """Selector bundle for resilient extraction."""

    title: tuple[str, ...]
    body: tuple[str, ...]
    published_at: tuple[str, ...]
    office_name: tuple[str, ...]
    reporter_name: tuple[str, ...]
    reporter_link: tuple[str, ...]
    reporter_page_items: tuple[str, ...]
    pagination_links: tuple[str, ...]


NAVER_SELECTORS = SelectorSet(
    title=(
        "h2#title_area",
        "h2.media_end_head_headline",
        "meta[property='og:title']",
    ),
    body=(
        "#dic_area",
        "#newsct_article",
        ".go_trans._article_content",
        "article#dic_area",
    ),
    published_at=(
        "span.media_end_head_info_datestamp_time._ARTICLE_DATE_TIME",
        "span#newsct_article_date",
        "meta[property='article:published_time']",
    ),
    office_name=(
        "a.media_end_head_top_logo img",
        "a.media_end_head_top_logo",
        "meta[property='me2:category1']",
    ),
    reporter_name=(
        "em.media_end_head_journalist_name",
        ".media_end_head_journalist_name",
        ".media_end_head_info_byline",
        "meta[name='byl']",
    ),
    reporter_link=(
        "a.media_end_head_journalist",
        "a[href*='/journalist/']",
        "a[href*='/reporter/']",
    ),
    reporter_page_items=(
        "a[href*='/article/']",
        "ul.type_list li a",
        "div.press_edit_news_item a",
        "div.list_area a",
    ),
    pagination_links=(
        "a.btn_next",
        "a[aria-label='다음']",
        "div.paging a",
    ),
)

REPORTER_DIRECTORY_PATTERNS = (
    "https://media.naver.com/press/{office_id}/reporter",
    "https://media.naver.com/journalists?officeId={office_id}",
)
