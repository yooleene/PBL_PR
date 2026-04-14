"""Orchestration service for search, verification, collection, and persistence."""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime

from sqlalchemy import select

from naver_reporter_app.analysis import ArticleAnalyzer
from naver_reporter_app.constants import POSCO_GROUP_KEYWORDS
from naver_reporter_app.extensions import db
from naver_reporter_app.llm import GeminiReporterAnalyzer
from naver_reporter_app.models import AnalysisRun, Article, Reporter
from naver_reporter_app.schemas import AnalyzeRequest, AnalyzeResponse, ArticleParseResult, ArticleSchema, ReporterPageItem, ReporterSchema
from naver_reporter_app.scrapers.article import NaverArticleScraper
from naver_reporter_app.scrapers.reporter import NaverReporterScraper
from naver_reporter_app.scrapers.search import NaverSearchScraper


class ReporterAnalysisService:
    """Coordinates the end-to-end collection pipeline."""

    def __init__(self) -> None:
        self.search_scraper = NaverSearchScraper()
        self.article_scraper = NaverArticleScraper()
        self.reporter_scraper = NaverReporterScraper()
        self.analyzer = ArticleAnalyzer()
        self.llm_analyzer = GeminiReporterAnalyzer()

    def run(self, payload: AnalyzeRequest) -> AnalyzeResponse:
        warnings: list[str] = []
        reporter = self._get_or_create_reporter(payload.office_name, payload.reporter_name)

        verified_search_articles: list[ArticleParseResult] = []
        search_queries = self.search_scraper.build_queries(payload.office_name, payload.reporter_name)

        if reporter.reporter_page_url:
            representative_reporter_url = reporter.reporter_page_url
        else:
            candidates = self.search_scraper.search_candidates(payload.office_name, payload.reporter_name)
            for candidate in candidates:
                try:
                    parsed = self.article_scraper.parse_article(candidate.url, payload.office_name, payload.reporter_name)
                except Exception:
                    continue
                if parsed.verified and parsed.published_date:
                    verified_search_articles.append(parsed)
            representative_reporter_url = self.reporter_scraper.select_representative_reporter_url(verified_search_articles)

        fallback_used = False
        if not representative_reporter_url:
            fallback_used = True
            office_id = self._select_office_id(verified_search_articles)
            representative_reporter_url = self.reporter_scraper.find_reporter_page_from_office_directory(
                office_id=office_id,
                reporter_name=payload.reporter_name,
            )
            if representative_reporter_url:
                warnings.append("기사 본문 링크가 없어 officeId 기반 fallback으로 기자 페이지를 추정했습니다.")
            else:
                warnings.append("기자 페이지 URL을 확보하지 못해 검증 기사 집합만으로 분석했습니다.")

        reporter.reporter_page_url = representative_reporter_url
        reporter.office_id = reporter.office_id or self._select_office_id(verified_search_articles)
        reporter.last_collected_at = datetime.utcnow()
        db.session.flush()

        page_items: list[ReporterPageItem] = []
        if representative_reporter_url:
            try:
                page_items = self.reporter_scraper.crawl_reporter_articles(
                    representative_reporter_url,
                    date_from=payload.date_from,
                    date_to=payload.date_to,
                    limit=payload.limit,
                )
            except Exception as exc:
                fallback_used = True
                warnings.append(f"기자 페이지 수집 중 오류가 발생해 검색 검증 기사만 사용했습니다: {exc}")

        final_verified_articles = self._reverify_reporter_items(
            page_items,
            office_name=payload.office_name,
            reporter_name=payload.reporter_name,
        )
        merged_articles = self._merge_article_sets(verified_search_articles, final_verified_articles)
        merged_articles = [article for article in merged_articles if article.published_date]
        merged_articles = [
            article for article in merged_articles if payload.date_from <= article.published_date <= payload.date_to
        ]
        merged_articles = sorted(merged_articles, key=lambda item: item.published_date, reverse=True)[: payload.limit]

        saved_articles = self._persist_articles(reporter, merged_articles)
        article_schemas = self._build_article_schemas(saved_articles)
        heuristic_analysis = self.analyzer.analyze(article_schemas)
        posco_articles = self._select_posco_articles(article_schemas)
        popular_articles = self._select_popular_articles(article_schemas)
        llm_analysis = self.llm_analyzer.analyze(payload.reporter_name, payload.office_name, article_schemas)

        run = AnalysisRun(
            reporter=reporter,
            requested_office_name=payload.office_name,
            requested_reporter_name=payload.reporter_name,
            date_from=payload.date_from,
            date_to=payload.date_to,
            requested_limit=payload.limit,
            article_count=len(saved_articles),
            reporter_page_url=representative_reporter_url,
            search_queries=search_queries,
            fallback_used=fallback_used,
            analysis_result={
                "heuristic": heuristic_analysis,
                "posco_articles": posco_articles,
                "popular_articles": popular_articles,
                "llm": llm_analysis,
            },
            warnings=warnings,
        )
        db.session.add(run)
        db.session.commit()

        return AnalyzeResponse(
            run_id=run.id,
            reporter=ReporterSchema.model_validate(reporter),
            article_count=len(saved_articles),
            articles=article_schemas,
            analysis=heuristic_analysis,
            posco_articles=posco_articles,
            popular_articles=popular_articles,
            llm_analysis=llm_analysis,
            warnings=warnings,
        )

    def _get_or_create_reporter(self, office_name: str, reporter_name: str) -> Reporter:
        reporter = db.session.execute(
            select(Reporter).where(Reporter.office_name == office_name, Reporter.reporter_name == reporter_name)
        ).scalar_one_or_none()
        if reporter:
            return reporter
        reporter = Reporter(office_name=office_name, reporter_name=reporter_name)
        db.session.add(reporter)
        db.session.flush()
        return reporter

    def _select_office_id(self, articles: list[ArticleParseResult]) -> str | None:
        office_ids = [article.office_id for article in articles if article.office_id]
        return office_ids[0] if office_ids else None

    def _reverify_reporter_items(
        self,
        items: list[ReporterPageItem],
        *,
        office_name: str,
        reporter_name: str,
    ) -> list[ArticleParseResult]:
        verified: list[ArticleParseResult] = []
        for item in items:
            try:
                parsed = self.article_scraper.parse_article(item.url, office_name, reporter_name)
            except Exception:
                continue
            if parsed.verified and parsed.published_date:
                verified.append(parsed)
        return verified

    def _merge_article_sets(
        self,
        search_articles: list[ArticleParseResult],
        reporter_articles: list[ArticleParseResult],
    ) -> list[ArticleParseResult]:
        merged = OrderedDict()
        for article in search_articles + reporter_articles:
            merged[article.url] = article
        return list(merged.values())

    def _persist_articles(self, reporter: Reporter, articles: list[ArticleParseResult]) -> list[Article]:
        saved: list[Article] = []
        for article in articles:
            existing = db.session.execute(select(Article).where(Article.url == article.url)).scalar_one_or_none()
            if existing:
                existing.title = article.title
                existing.body = article.body
                existing.office_name = article.office_name or reporter.office_name
                existing.reporter_name = article.reporter_name or reporter.reporter_name
                existing.reporter_page_url = article.reporter_page_url
                existing.category = article.category
                existing.published_date = article.published_date
                existing.verified = article.verified
                existing.raw_metadata = article.raw_metadata
                saved.append(existing)
                continue
            model = Article(
                reporter=reporter,
                url=article.url,
                title=article.title,
                body=article.body,
                office_name=article.office_name or reporter.office_name,
                reporter_name=article.reporter_name or reporter.reporter_name,
                reporter_page_url=article.reporter_page_url,
                category=article.category,
                published_date=article.published_date,
                verified=article.verified,
                source_type="reporter_page" if article.reporter_page_url == reporter.reporter_page_url else "search",
                raw_metadata=article.raw_metadata,
            )
            db.session.add(model)
            saved.append(model)
        db.session.flush()
        return saved

    def _build_article_schemas(self, articles: list[Article]) -> list[ArticleSchema]:
        result: list[ArticleSchema] = []
        for article in articles:
            metadata = article.raw_metadata or {}
            result.append(
                ArticleSchema(
                    url=article.url,
                    title=article.title,
                    body=article.body,
                    office_name=article.office_name,
                    reporter_name=article.reporter_name,
                    published_date=article.published_date,
                    reporter_page_url=article.reporter_page_url,
                    category=article.category,
                    verified=article.verified,
                    source_type=article.source_type,
                    special_label=metadata.get("special_label"),
                    comment_count=metadata.get("comment_count"),
                    raw_metadata=metadata,
                )
            )
        return result

    def _select_posco_articles(self, articles: list[ArticleSchema]) -> list[dict]:
        matched = [
            article for article in articles if any(keyword in article.title or keyword in article.body for keyword in POSCO_GROUP_KEYWORDS)
        ]
        matched = sorted(matched, key=lambda article: article.published_date, reverse=True)[:10]
        return [
            {
                "title": article.title,
                "published_date": article.published_date.isoformat(),
                "url": article.url,
                "special_label": article.special_label,
            }
            for article in matched
        ]

    def _select_popular_articles(self, articles: list[ArticleSchema]) -> list[dict]:
        candidates = [article for article in articles if (article.comment_count or 0) > 0]
        ranked = sorted(candidates, key=lambda article: ((article.comment_count or 0), article.published_date), reverse=True)
        selected = sorted(ranked[:5], key=lambda article: article.published_date, reverse=True)
        return [
            {
                "title": article.title,
                "published_date": article.published_date.isoformat(),
                "url": article.url,
                "comment_count": article.comment_count,
                "special_label": article.special_label,
            }
            for article in selected
        ]
