# 네이버 기자 분석 웹앱 — 프로젝트 프롬프트

> 이 문서는 개발 과정에서 확정된 요구사항·설계 결정·수정 이력을 담은 프롬프트용 레퍼런스입니다.

---

## 1. 프로젝트 개요

포스코 홍보 담당자가 네이버 뉴스에 등록된 기자를 검색하고, 해당 기자의 기사를 수집·분석하여 미팅 전 사전 조사를 자동화하는 내부 웹 애플리케이션.

---

## 2. 기술 스택

| 항목 | 선택 |
|------|------|
| 백엔드 | Python 3 + Flask |
| 크롤링 | Playwright (Chromium headless) + BeautifulSoup4 |
| AI 분석 | Google Gemini API (`gemini-2.0-flash`) |
| 프론트엔드 | Bootstrap 5 (PC + 모바일 반응형) |
| 환경변수 | `.env` 파일 (python-dotenv) |

---

## 3. 프로젝트 파일 구조

```
proj1/
├── app.py                    # Flask 메인 앱 (라우팅, 백그라운드 스레드)
├── requirements.txt          # 패키지 목록
├── .env                      # API 키 및 설정 (Git 제외)
├── utils/
│   ├── __init__.py
│   ├── crawler.py            # Playwright 기반 네이버 크롤러
│   └── analyzer.py           # Gemini AI 분석 모듈
├── templates/
│   ├── base.html             # 공통 레이아웃 (Navbar, Footer)
│   ├── index.html            # 검색 화면
│   ├── progress.html         # 진행 상황 (폴링 방식)
│   └── result.html           # 분석 결과 (4개 탭)
└── static/
    ├── css/style.css
    └── js/main.js
```

---

## 4. .env 파일 구성

```
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=change-this-secret

GOOGLE_API_KEY=<Gemini API Key>
GEMINI_MODEL=gemini-2.0-flash

REQUEST_TIMEOUT=12
MAX_ARTICLES=30
```

---

## 5. 실행 방법

```bash
pip install -r requirements.txt
playwright install chromium
python app.py
# → http://localhost:5001 접속
```

---

## 6. 네이버 기자 페이지 구조 (크롤링 대상)

| 항목 | URL / 설명 |
|------|-----------|
| 기자 목록 | `https://media.naver.com/journalists/whole?officeId=001` |
| officeId 범위 | `001` ~ `099` |
| 개별 기자 페이지 | `https://media.naver.com/journalist/{id}/` |
| 기자 목록 스크롤 | **무한 스크롤** 방식 (10회 스크롤로 전체 탐색) |
| 기자 기사 목록 | 기자 페이지 내 **5회 스크롤**로 전체 수집 |
| 기사 원문 | `https://n.news.naver.com/article/...` |

---

## 7. 크롤러 동작 흐름 (crawler.py)

### Step 1 — 매체 officeId 탐색
- `officeId` 001 ~ 099 순차 순회
- 각 페이지 로드 후 **1.2초 대기** (JS 렌더링)
- 매체명 감지 우선순위:
  1. `<title>` 태그 (예: "조선일보 기자 - 네이버 뉴스")
  2. `h1 / h2 / h3 / strong / b` 헤더 요소
  3. CSS 클래스명에 `press / office / media / name / title` 포함 요소

### Step 2 — 기자 검색 (무한 스크롤 10회)
- 해당 officeId 기자 목록 페이지 로드
- 스크롤 전 1회 + 10회 스크롤, 매 스크롤 후 1초 대기
- 기자명 매칭 우선순위:
  1. `journalist` URL + 이름 **정확 일치**
  2. `journalist` URL + 이름 **포함**
  3. 텍스트 이름 포함 (URL 무관)

### Step 3 — 기사 수집 (5회 스크롤)
- 기자 페이지에서 `전체 기사` 탭 클릭 시도 후 **5회 스크롤**
- 수집된 전체 기사에서:
  - **최신 20건**: 관심분야·논조·키워드 분석용 원문 수집
  - **포스코 관련 5건**: 제목 키워드 필터 → 토킹포인트 생성용 원문 수집
- 포스코 필터 키워드: `포스코, POSCO, 포항제철, 포스코홀딩스, 포스코퓨처엠, 포스코인터내셔널, 포스코건설, 포스코케미칼`

### 기사 원문 선택자 (우선순위 순)
```
div#dic_area
div.newsct_article / .go_trans / .article_body
div#articleBodyContents
article
div.news_body / .content_body / .article-body
```

---

## 8. AI 분석 흐름 (analyzer.py)

Gemini를 **2회 분리 호출**하여 분석 정확도 향상:

### 호출 1 — 일반 분석 (최신 기사 20건 입력)
반환 JSON 구조:
```json
{
  "interest_areas": [{"area": "...", "description": "..."}],
  "article_tone": {
    "overall": "...",
    "characteristics": ["...", "...", "..."],
    "stance": "비판적 | 중립적 | 우호적"
  },
  "recent_keywords": [
    {"keyword": "...", "frequency": "높음 | 중간 | 낮음", "context": "..."}
  ]
}
```

### 호출 2 — 토킹포인트 (포스코 기사 5건 입력)
포스코 기사가 없으면 일반 기사 기반으로 대체 생성.
반환 JSON 구조:
```json
{
  "posco_coverage": {
    "has_posco_articles": true,
    "posco_tone": "...",
    "posco_topics": ["...", "..."],
    "posco_summary": "..."
  },
  "talking_points": [
    {"title": "...", "content": "...", "rationale": "..."}
  ],
  "meeting_strategy": "..."
}
```
- `talking_points`: 항상 정확히 **5개** 생성
- 기사 본문이 없으면 제목만으로도 분석 (프롬프트에 `(본문 미수집)` 표시)
- Gemini 응답에서 코드블록(` ``` `) 제거 후 JSON 파싱, 실패 시 정규식으로 재추출

---

## 9. Flask 앱 구조 (app.py)

| 라우트 | 설명 |
|--------|------|
| `GET /` | 검색 화면 |
| `POST /search` | 검색 폼 수신 → 백그라운드 스레드 시작 → `/progress/<job_id>` 리다이렉트 |
| `GET /progress/<job_id>` | 진행 상황 페이지 |
| `GET /api/status/<job_id>` | 폴링용 JSON API (`status / progress / message / error`) |
| `GET /result/<job_id>` | 분석 결과 페이지 |

- 작업은 `threading.Thread`로 백그라운드 실행
- 진행 상황은 2초 간격 **폴링** 방식으로 프론트에 전달
- 결과는 인메모리 딕셔너리(`JOBS`)에 저장 (프로덕션 전환 시 Redis 권장)
- 포트: **5001**

---

## 10. 결과 화면 구성 (result.html)

4개 탭으로 구성:

| 탭 | 내용 |
|----|------|
| 종합 분석 | 관심 분야 / 기사 논조 / 최근 관심 키워드 |
| 최신 기사 | 최신 기사 최대 20건 (제목 + 날짜 + 원문 링크) |
| 포스코 기사 | 포스코 관련 최신 기사 최대 5건 + 포스코 보도 성향 요약 |
| 토킹포인트 | 미팅 전략 개요 + 핵심 토킹포인트 5개 (제목·내용·활용이유) |

---

## 11. 주요 수정 이력

| 차수 | 수정 내용 |
|------|----------|
| 1차 | 포트 5000 → **5001** 변경 |
| 2차 | 기자 검색: 정적 HTML 파싱 → **무한 스크롤 10회** 방식으로 변경 |
| 3차 | officeId 탐색 범위 1~200 → **1~99** 로 축소, 매체명 감지 3단계 우선순위 정립 |
| 4차 | 포스코 기사: 기자 페이지 **5회 스크롤** 후 제목 키워드 필터로 수집 |
| 4차 | Gemini 호출 **1회 통합 → 2회 분리** (일반분석 / 토킹포인트) |
| 4차 | 기사 본문 없을 때도 제목 기반 분석 가능하도록 프롬프트 수정 |
| 4차 | `posco_articles_raw`를 crawler → app.py → analyzer로 전달 경로 확립 |

---

## 12. 향후 개선 고려사항

- 매체명-officeId 매핑 테이블 캐싱 (매번 001~099 순회 비효율 개선)
- 작업 결과 Redis 또는 DB 저장 (서버 재시작 시 결과 유실 방지)
- 기사 본문 수집 실패율 모니터링 및 재시도 로직
- 분석 결과 PDF/Word 내보내기 기능
- 기자 즐겨찾기 및 이전 분석 결과 이력 조회
