"""
네이버 기자 검색 및 기사 수집 크롤러
Playwright 기반 비동기 크롤러
"""

import asyncio
import os
import re
from typing import Optional, List, Dict, Callable
from playwright.async_api import async_playwright, Page
from bs4 import BeautifulSoup

# 포스코 관련 키워드
POSCO_KEYWORDS = [
    "포스코", "POSCO", "포항제철", "포스코홀딩스", "포스코퓨처엠",
    "포스코인터내셔널", "포스코건설", "포스코케미칼", "포항스틸",
]


def _is_posco_title(title: str) -> bool:
    t = title.upper()
    return any(k.upper() in t for k in POSCO_KEYWORDS)


class NaverJournalistCrawler:
    BASE_URL = "https://media.naver.com"
    JOURNALIST_LIST_URL = "https://media.naver.com/journalists/whole"
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(self, progress_callback: Optional[Callable] = None):
        self.progress_callback = progress_callback
        self.headless = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() in {
            "1", "true", "yes", "on"
        }
        self.browser_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
        ]
        self.user_agent = os.getenv("PLAYWRIGHT_USER_AGENT", self.DEFAULT_USER_AGENT)
        self.locale = os.getenv("PLAYWRIGHT_LOCALE", "ko-KR")
        self.viewport = {
            "width": int(os.getenv("PLAYWRIGHT_VIEWPORT_WIDTH", "1280")),
            "height": int(os.getenv("PLAYWRIGHT_VIEWPORT_HEIGHT", "800")),
        }
        self.executable_path = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH") or None

    def _update(self, message: str, percent: int):
        if self.progress_callback:
            self.progress_callback(message, percent)

    # ------------------------------------------------------------------ #
    #  공개 API
    # ------------------------------------------------------------------ #

    def search_journalist(self, media_name: str, journalist_name: str) -> Dict:
        return asyncio.run(self._async_search(media_name, journalist_name))

    # ------------------------------------------------------------------ #
    #  비동기 메인 흐름
    # ------------------------------------------------------------------ #

    async def _async_search(self, media_name: str, journalist_name: str) -> Dict:
        async with async_playwright() as p:
            launch_kwargs = {
                "headless": self.headless,
                "args": self.browser_args,
            }
            if self.executable_path:
                launch_kwargs["executable_path"] = self.executable_path

            browser = await p.chromium.launch(**launch_kwargs)
            context = await browser.new_context(
                user_agent=self.user_agent,
                locale=self.locale,
                viewport=self.viewport,
            )
            page = await context.new_page()

            try:
                # 1단계: 매체 officeId 탐색
                self._update(f"'{media_name}' 매체 검색 중…", 5)
                office_id = await self._find_office_id(page, media_name)
                if not office_id:
                    return {"error": f"'{media_name}' 매체를 네이버에서 찾을 수 없습니다."}

                # 2단계: 기자 URL 탐색 (스크롤 10회)
                self._update(f"'{journalist_name}' 기자 검색 중…", 20)
                journalist_info = await self._find_journalist(page, office_id, journalist_name)
                if not journalist_info:
                    return {"error": f"'{media_name}'에서 '{journalist_name}' 기자를 찾을 수 없습니다."}

                # 3단계: 기사 수집
                self._update("기자 페이지 로딩 중…", 35)
                result = await self._collect_journalist_data(page, journalist_info)
                return result

            except Exception as e:
                return {"error": f"크롤링 오류: {str(e)}"}
            finally:
                await browser.close()

    # ------------------------------------------------------------------ #
    #  매체 officeId 탐색 (001 ~ 057)
    # ------------------------------------------------------------------ #

    async def _find_office_id(self, page: Page, media_name: str) -> Optional[str]:
        for i in range(1, 58):
            office_id = str(i).zfill(3)
            url = f"{self.JOURNALIST_LIST_URL}?officeId={office_id}"
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=12000)
                if resp and resp.status in (404, 403):
                    continue
                await page.wait_for_timeout(1200)
                content = await page.content()
                soup = BeautifulSoup(content, "lxml")

                # 1순위: <title> 태그
                if soup.title and soup.title.string and media_name in soup.title.string:
                    return office_id
                # 2순위: 헤더 요소
                for tag in soup.find_all(["h1", "h2", "h3", "strong", "b"]):
                    if media_name in tag.get_text(strip=True):
                        return office_id
                # 3순위: press/office/media 관련 클래스
                for elem in soup.find_all(class_=re.compile(r"press|office|media|name|title", re.I)):
                    if media_name in elem.get_text(strip=True):
                        return office_id
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------ #
    #  기자 검색 (스크롤 10회)
    # ------------------------------------------------------------------ #

    async def _find_journalist(self, page: Page, office_id: str, journalist_name: str) -> Optional[Dict]:
        url = f"{self.JOURNALIST_LIST_URL}?officeId={office_id}"
        try:
            await page.goto(url, wait_until="networkidle", timeout=20000)
        except Exception:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(1500)

        MAX_SCROLL = 10
        for scroll_idx in range(MAX_SCROLL + 1):
            content = await page.content()
            soup = BeautifulSoup(content, "lxml")
            result = self._search_journalist_in_soup(soup, journalist_name, office_id)
            if result:
                return result
            if scroll_idx < MAX_SCROLL:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)
        return None

    def _search_journalist_in_soup(self, soup, journalist_name, office_id) -> Optional[Dict]:
        # 1순위: journalist URL + 이름 정확 일치
        for a in soup.find_all("a", href=True):
            if "journalist" in a["href"] and a.get_text(strip=True) == journalist_name:
                href = a["href"]
                return {"name": journalist_name,
                        "url": href if href.startswith("http") else self.BASE_URL + href,
                        "office_id": office_id}
        # 2순위: journalist URL + 이름 포함
        for a in soup.find_all("a", href=True):
            if "journalist" in a["href"] and journalist_name in a.get_text(strip=True):
                href = a["href"]
                return {"name": journalist_name,
                        "url": href if href.startswith("http") else self.BASE_URL + href,
                        "office_id": office_id}
        # 3순위: 이름 포함 (href 무관)
        for a in soup.find_all("a", href=True):
            if journalist_name in a.get_text():
                href = a["href"]
                return {"name": journalist_name,
                        "url": href if href.startswith("http") else self.BASE_URL + href,
                        "office_id": office_id}
        return None

    # ------------------------------------------------------------------ #
    #  기자 데이터 수집 (핵심)
    # ------------------------------------------------------------------ #

    async def _collect_journalist_data(self, page: Page, journalist_info: Dict) -> Dict:
        journalist_url = journalist_info["url"]

        try:
            await page.goto(journalist_url, wait_until="networkidle", timeout=20000)
        except Exception:
            await page.goto(journalist_url, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)

        # 프로필
        soup0 = BeautifulSoup(await page.content(), "lxml")
        profile = self._extract_profile(soup0, journalist_info["name"])

        # ── 기사 목록 수집: 5회 스크롤 ──────────────────────────────────
        self._update("기사 목록 수집 중 (5회 스크롤)…", 42)
        all_articles = await self._scroll_and_collect(page, scroll_count=5)

        # 최신 기사 20건 (분석용)
        latest_20 = all_articles[:20]

        # 포스코 관련 기사: 제목 기준 필터, 최대 5건
        posco_articles = [a for a in all_articles if _is_posco_title(a["title"])][:5]

        # ── 최신 20건 원문 수집 ──────────────────────────────────────────
        total = len(latest_20)
        for i, art in enumerate(latest_20):
            pct = 50 + int((i / max(total, 1)) * 25)
            self._update(f"기사 원문 수집 중… ({i+1}/{total})", pct)
            art["full_content"] = await self._fetch_article_content(page, art["url"])
            await asyncio.sleep(0.3)

        # ── 포스코 기사 원문 수집 (최신 20건과 중복 제외) ────────────────
        latest_urls = {a["url"] for a in latest_20}
        for i, art in enumerate(posco_articles):
            if art["url"] in latest_urls:
                # 이미 수집된 경우 복사
                for la in latest_20:
                    if la["url"] == art["url"]:
                        art["full_content"] = la["full_content"]
                        break
            else:
                self._update(f"포스코 기사 수집 중… ({i+1}/{len(posco_articles)})", 78 + i * 2)
                art["full_content"] = await self._fetch_article_content(page, art["url"])
                await asyncio.sleep(0.3)

        self._update("데이터 수집 완료", 90)

        return {
            "journalist_name": journalist_info["name"],
            "journalist_url": journalist_url,
            "office_id": journalist_info["office_id"],
            "profile": profile,
            "articles": latest_20,            # 최신 20건 (분석용)
            "posco_articles_raw": posco_articles,  # 포스코 기사 (토킹포인트용)
        }

    # ------------------------------------------------------------------ #
    #  스크롤하며 기사 목록 수집
    # ------------------------------------------------------------------ #

    async def _scroll_and_collect(self, page: Page, scroll_count: int = 5) -> List[Dict]:
        """
        기자 페이지에서 scroll_count회 스크롤하며 기사 링크 수집.
        초기 로드 포함 총 (scroll_count+1)회 파싱.
        """
        seen: set = set()
        articles: List[Dict] = []

        # 초기에 '전체 기사' 탭 클릭 시도
        try:
            btn = (await page.query_selector("text=전체 기사") or
                   await page.query_selector("a:has-text('전체')"))
            if btn:
                await btn.click()
                await page.wait_for_timeout(1500)
        except Exception:
            pass

        for i in range(scroll_count + 1):
            soup = BeautifulSoup(await page.content(), "lxml")
            new_arts = self._extract_links_from_soup(soup, seen)
            articles.extend(new_arts)
            for a in new_arts:
                seen.add(a["url"])

            if i < scroll_count:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)

        return articles

    def _extract_links_from_soup(self, soup: BeautifulSoup, seen: set) -> List[Dict]:
        """soup에서 news.naver 링크를 추출, seen에 없는 것만 반환"""
        result = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not re.search(r"news\.naver", href):
                continue
            full_url = href if href.startswith("http") else "https:" + href
            if full_url in seen:
                continue

            # 제목
            title = a.get_text(strip=True)
            if not title or len(title) < 5:
                parent = a.parent
                if parent:
                    t = parent.find("strong") or parent.find("span")
                    if t:
                        title = t.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # 날짜 (부모 3단계까지 탐색)
            date = ""
            p = a.parent
            for _ in range(3):
                if p is None:
                    break
                de = p.find(["span", "em", "time"], class_=re.compile(r"date|time|ago", re.I))
                if de:
                    date = de.get_text(strip=True)
                    break
                if p.get("datetime"):
                    date = p["datetime"]
                    break
                p = p.parent

            result.append({"title": title, "url": full_url, "date": date,
                            "summary": "", "full_content": ""})
        return result

    # ------------------------------------------------------------------ #
    #  프로필 추출
    # ------------------------------------------------------------------ #

    def _extract_profile(self, soup: BeautifulSoup, name: str) -> Dict:
        profile = {"name": name, "media": "", "photo_url": "", "description": ""}

        for img in soup.find_all("img"):
            src = img.get("src", "")
            if name in img.get("alt", "") or "journalist" in src.lower():
                profile["photo_url"] = src
                break

        for elem in soup.find_all(class_=re.compile(r"office|press|media|company", re.I)):
            text = elem.get_text(strip=True)
            if text and len(text) < 30:
                profile["media"] = text
                break

        for elem in soup.find_all(["p", "div"], class_=re.compile(r"desc|intro|about|bio", re.I)):
            text = elem.get_text(strip=True)
            if len(text) > 10:
                profile["description"] = text[:300]
                break

        return profile

    # ------------------------------------------------------------------ #
    #  기사 원문 수집
    # ------------------------------------------------------------------ #

    async def _fetch_article_content(self, page: Page, url: str) -> str:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(800)
            soup = BeautifulSoup(await page.content(), "lxml")

            selectors = [
                ("div", {"id": "dic_area"}),
                ("div", {"class": re.compile(r"newsct_article|go_trans|article_body", re.I)}),
                ("div", {"id": "articleBodyContents"}),
                ("article", {}),
                ("div", {"class": re.compile(r"news_body|content_body|article-body", re.I)}),
            ]
            for tag, attrs in selectors:
                elem = soup.find(tag, attrs)
                if elem:
                    for junk in elem.find_all(["script", "style", "figure", "iframe"]):
                        junk.decompose()
                    text = elem.get_text(separator="\n", strip=True)
                    if len(text) > 100:
                        return text
            return ""
        except Exception:
            return ""
