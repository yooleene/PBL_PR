"""Gemini-backed reporter insight generation."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests
from flask import current_app

from naver_reporter_app.constants import POSCO_GROUP_COMPANIES, POSCO_GROUP_KEYWORDS
from naver_reporter_app.schemas import ArticleSchema

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiReporterAnalyzer:
    """Use Gemini to derive journalist interest, tone, and talking points."""

    def analyze(self, reporter_name: str, office_name: str, articles: list[ArticleSchema]) -> dict[str, Any]:
        """Return a structured Gemini analysis with graceful fallback."""
        if not articles:
            return self._fallback_payload("분석 가능한 기사 데이터가 없습니다.", [], [], [])

        posco_articles = self._select_posco_articles(articles)[:10]
        popular_articles = self._select_popular_articles(articles)[:5]

        api_key = current_app.config.get("GOOGLE_API_KEY", "")
        if not api_key:
            return self._fallback_payload("GOOGLE_API_KEY가 없어 규칙 기반 분석으로 대체했습니다.", articles, posco_articles, popular_articles)

        prompt = self._build_prompt(reporter_name, office_name, articles, posco_articles, popular_articles)
        try:
            response = requests.post(
                GEMINI_API_URL.format(model=current_app.config["GEMINI_MODEL"]),
                params={"key": api_key},
                json=prompt,
                timeout=current_app.config["GEMINI_TIMEOUT"],
            )
            response.raise_for_status()
            payload = response.json()
            text = (
                payload.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            data = json.loads(text)
            data.setdefault("interest_areas", [])
            data.setdefault("tone_analysis", "")
            data.setdefault("meeting_talking_points", [])
            return data
        except Exception as exc:  # pragma: no cover - network path
            logger.warning("Gemini analysis failed: %s", exc)
            return self._fallback_payload(f"Gemini 분석 실패로 규칙 기반 분석으로 대체했습니다: {exc}", articles, posco_articles, popular_articles)

    def _build_prompt(
        self,
        reporter_name: str,
        office_name: str,
        articles: list[ArticleSchema],
        posco_articles: list[ArticleSchema],
        popular_articles: list[ArticleSchema],
    ) -> dict[str, Any]:
        base_articles = [
            {
                "title": article.title,
                "published_date": article.published_date.isoformat(),
                "body_excerpt": article.body[:1000],
                "special_label": article.special_label,
                "comment_count": article.comment_count,
                "url": article.url,
            }
            for article in articles[:20]
        ]
        posco_rows = [self._brief(article) for article in posco_articles]
        popular_rows = [self._brief(article, include_comments=True) for article in popular_articles]
        instruction = {
            "reporter_name": reporter_name,
            "office_name": office_name,
            "task": [
                "관심분야를 3~6개 문자열 배열로 반환",
                "기사 논조를 4~6문장으로 반환",
                "포스코그룹 사업회사별 기자 관심사를 반영한 미팅 토킹포인트를 객체 배열로 반환",
            ],
            "output_schema": {
                "interest_areas": ["string"],
                "tone_analysis": "string",
                "meeting_talking_points": [
                    {
                        "company": "string",
                        "interest_topic": "string",
                        "conversation_point": "string",
                        "issue_watch": "string",
                    }
                ],
            },
        }
        body = {
            "instruction": instruction,
            "articles": base_articles,
            "posco_article_candidates": posco_rows,
            "popular_article_candidates": popular_rows,
            "posco_keywords": list(POSCO_GROUP_KEYWORDS),
            "posco_companies": list(POSCO_GROUP_COMPANIES),
            "return_json_only": True,
        }
        return {
            "contents": [{"parts": [{"text": json.dumps(body, ensure_ascii=False)}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.4,
            },
        }

    def _fallback_payload(
        self,
        notice: str,
        articles: list[ArticleSchema],
        posco_articles: list[ArticleSchema],
        popular_articles: list[ArticleSchema],
    ) -> dict[str, Any]:
        return {
            "analysis_notice": notice,
            "interest_areas": self._derive_interest_areas(articles),
            "tone_analysis": (
                "최근 기사 키워드와 제목 패턴 기준으로 볼 때 현안 추적형 보도 비중이 높고, "
                "사안 설명 중심의 정보 전달형 논조가 두드러집니다."
            ),
            "meeting_talking_points": [
                {
                    "company": company,
                    "interest_topic": "최근 보도 기사와 연결되는 사업 현안",
                    "conversation_point": f"{company} 관련 투자, 공급망, 실적, 정책 변화 이슈를 기사 맥락과 연결해 대화",
                    "issue_watch": "수익성, 투자 계획, 규제, 시장 반응을 함께 점검",
                }
                for company in POSCO_GROUP_COMPANIES
            ],
        }

    def _derive_interest_areas(self, articles: list[ArticleSchema]) -> list[str]:
        scores: dict[str, int] = {}
        for article in articles:
            for keyword in POSCO_GROUP_KEYWORDS:
                if keyword in article.title or keyword in article.body:
                    scores[keyword] = scores.get(keyword, 0) + 1
        if not scores:
            for article in articles:
                token = article.category or article.office_name
                scores[token] = scores.get(token, 0) + 1
        return [keyword for keyword, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:5]]

    def _select_posco_articles(self, articles: list[ArticleSchema]) -> list[ArticleSchema]:
        matched = [
            article
            for article in articles
            if any(keyword in article.title or keyword in article.body for keyword in POSCO_GROUP_KEYWORDS)
        ]
        return sorted(matched, key=lambda article: article.published_date, reverse=True)

    def _select_popular_articles(self, articles: list[ArticleSchema]) -> list[ArticleSchema]:
        candidates = [article for article in articles if (article.comment_count or 0) > 0]
        ranked = sorted(candidates, key=lambda article: ((article.comment_count or 0), article.published_date), reverse=True)
        return sorted(ranked[:5], key=lambda article: article.published_date, reverse=True)

    def _brief(self, article: ArticleSchema, *, include_comments: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": article.title,
            "published_date": article.published_date.isoformat(),
            "url": article.url,
        }
        if include_comments:
            payload["comment_count"] = article.comment_count
        return payload
