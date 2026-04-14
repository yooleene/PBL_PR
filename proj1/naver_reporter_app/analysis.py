"""Lightweight heuristic analysis."""

from __future__ import annotations

from collections import Counter, defaultdict

from naver_reporter_app.schemas import ArticleSchema
from naver_reporter_app.utils.text import count_tokens, tokenize_korean_text


class ArticleAnalyzer:
    """Prototype analyzer using lightweight heuristics.

    TODO: Upgrade to KoNLPy, Kiwi, SentenceTransformer, and LLM summarization.
    """

    def analyze(self, articles: list[ArticleSchema]) -> dict:
        """Generate a compact analysis payload."""
        titles = [article.title for article in articles]
        all_texts = [f"{article.title} {article.body}" for article in articles]

        return {
            "top_keywords": count_tokens(all_texts, top_n=15),
            "title_patterns": self._analyze_title_patterns(titles),
            "daily_counts": self._group_daily_counts(articles),
            "topic_clusters": self._topic_clusters(all_texts),
            "summary": self._build_summary(articles),
        }

    def _analyze_title_patterns(self, titles: list[str]) -> dict:
        if not titles:
            return {"question_style": 0, "quote_style": 0, "bracket_style": 0, "average_length": 0}
        return {
            "question_style": sum("?" in title for title in titles),
            "quote_style": sum(("\"" in title) or ("“" in title) or ("'" in title) for title in titles),
            "bracket_style": sum(("[" in title) or ("(" in title) for title in titles),
            "average_length": round(sum(len(title) for title in titles) / len(titles), 1),
        }

    def _group_daily_counts(self, articles: list[ArticleSchema]) -> list[tuple[str, int]]:
        counter = Counter(article.published_date.isoformat() for article in articles)
        return sorted(counter.items(), key=lambda item: item[0], reverse=True)

    def _topic_clusters(self, texts: list[str]) -> list[dict]:
        seed_groups: dict[str, list[str]] = {
            "정치/행정": ["정부", "대통령", "국회", "정책", "장관"],
            "경제/산업": ["경제", "시장", "기업", "금융", "수출", "산업"],
            "사회/사건": ["경찰", "법원", "사건", "사고", "수사"],
            "국제": ["미국", "중국", "일본", "유럽", "외교"],
        }
        grouped: dict[str, int] = defaultdict(int)
        unmatched = 0
        for text in texts:
            matched = False
            token_set = set(tokenize_korean_text(text))
            for topic_name, keywords in seed_groups.items():
                if token_set.intersection({keyword.lower() for keyword in keywords}):
                    grouped[topic_name] += 1
                    matched = True
                    break
            if not matched:
                unmatched += 1
        result = [{"topic": topic, "count": count} for topic, count in grouped.items()]
        if unmatched:
            result.append({"topic": "기타", "count": unmatched})
        return sorted(result, key=lambda item: item["count"], reverse=True)

    def _build_summary(self, articles: list[ArticleSchema]) -> str:
        if not articles:
            return "분석 가능한 검증 기사 데이터가 없습니다."
        keywords = ", ".join(keyword for keyword, _ in count_tokens([f"{a.title} {a.body}" for a in articles], top_n=5))
        start_date = min(article.published_date for article in articles).isoformat()
        end_date = max(article.published_date for article in articles).isoformat()
        return (
            f"총 {len(articles)}건의 검증 기사를 분석했다. "
            f"기간은 {start_date}부터 {end_date}까지이며 주요 키워드는 {keywords}이다."
        )
