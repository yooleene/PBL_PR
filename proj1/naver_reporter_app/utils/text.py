"""Text normalization and lightweight analysis helpers."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date

from naver_reporter_app.constants import KOREAN_STOPWORDS

WHITESPACE_RE = re.compile(r"\s+")
TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}")
DATE_RE = re.compile(r"(\d{4})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})")


def normalize_whitespace(value: str | None) -> str:
    """Collapse whitespace safely."""
    if not value:
        return ""
    return WHITESPACE_RE.sub(" ", value).strip()


def normalize_name(value: str | None) -> str:
    """Normalize personal names while tolerating whitespace variations."""
    value = normalize_whitespace(value)
    return re.sub(r"[^가-힣A-Za-z]", "", value)


def normalize_office_name(value: str | None) -> str:
    """Normalize publisher names."""
    value = normalize_whitespace(value)
    return re.sub(r"\s+", "", value)


def names_match(expected: str, actual: str | None) -> bool:
    """Allow exact and whitespace-tolerant matches."""
    normalized_expected = normalize_name(expected)
    normalized_actual = normalize_name(actual)
    if not normalized_expected or not normalized_actual:
        return False
    return (
        normalized_expected == normalized_actual
        or normalized_expected in normalized_actual
        or normalized_actual in normalized_expected
    )


def offices_match(expected: str, actual: str | None) -> bool:
    """Check office match with spacing tolerance."""
    normalized_expected = normalize_office_name(expected)
    normalized_actual = normalize_office_name(actual)
    return bool(normalized_expected and normalized_actual and normalized_expected == normalized_actual)


def extract_date(value: str | None) -> date | None:
    """Extract a date from a Korean timestamp string."""
    if not value:
        return None
    match = DATE_RE.search(value)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def tokenize_korean_text(text: str) -> list[str]:
    """Simple tokenization for prototype analysis.

    TODO: Replace with Kiwi or KoNLPy for more precise noun extraction.
    """
    tokens = [token.lower() for token in TOKEN_RE.findall(normalize_whitespace(text))]
    return [token for token in tokens if token not in KOREAN_STOPWORDS and len(token) > 1]


def count_tokens(texts: list[str], top_n: int = 20) -> list[tuple[str, int]]:
    """Return token frequency pairs."""
    counter = Counter()
    for text in texts:
        counter.update(tokenize_korean_text(text))
    return counter.most_common(top_n)
