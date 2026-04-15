# 네이버 기자 기사 분석 앱 프로토타입

Flask 기반 웹 앱 프로토타입이다. 사용자가 언론사명, 기자명, 조회 기간, 수집 개수를 입력하면 네이버 검색을 통해 기자 후보 기사를 찾고, 기사 본문을 검증한 뒤 기자 페이지를 확보하여 기사 목록을 재수집하고 간단한 텍스트 분석 결과를 제공한다.

## 프로젝트 개요

- 목표: `검색 -> 기사 검증 -> 기자 페이지 확보 -> 기자 페이지 기사 수집 -> 재검증 -> 분석` 흐름을 서비스 프로토타입 수준으로 구현
- 언어/프레임워크: Python, Flask, SQLAlchemy, requests, BeautifulSoup
- 데이터베이스: macOS 기본 SQLite, Cloud Run에서는 Cloud SQL PostgreSQL 권장
- 동적 페이지 대응: 기본은 `requests + BeautifulSoup`, 필요 시 Playwright fallback

## 주요 기능

- 네이버 검색 결과에서 뉴스 기사 후보 URL 수집
- 기사 본문에서 언론사, 기자명, 발행일, 기자 링크 검증
- 검증 기사 기반 기자 페이지 URL 대표값 선정 및 fallback 전략 수행
- 기자 페이지 페이지네이션 수집
- 기간 필터, limit, 중복 제거
- 수집 기사에 대한 재검증
- 특집성 기사 라벨(`단독`, `기획`, `르포`, `기자수첩`, `논설`, `사설`, `오피니언`) 표시
- 해당 기자의 포스코그룹 관련 기사 최신 10건 표시
- 해당 기자의 댓글 반응이 좋은 기사 최신 5건 표시
- 키워드, 제목 패턴, 날짜별 기사 수, 주제 묶음, 전체 요약 생성
- Gemini 기반 관심분야, 기사 논조, 미팅 토킹포인트 생성
- 분석 실행 이력과 기사 저장

## 디렉터리 구조

```text
.
├── app.py
├── requirements.txt
├── sample_request.json
├── README.md
└── naver_reporter_app
    ├── __init__.py
    ├── analysis.py
    ├── config.py
    ├── constants.py
    ├── extensions.py
    ├── logging_config.py
    ├── models.py
    ├── routes.py
    ├── schemas.py
    ├── scrapers
    │   ├── article.py
    │   ├── base.py
    │   ├── reporter.py
    │   └── search.py
    ├── services
    │   └── collector.py
    ├── templates
    │   ├── index.html
    │   └── result.html
    └── utils
        └── text.py
```

## 실행 방법

1. 가상환경 생성 및 활성화

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. 의존성 설치

```bash
pip install -r requirements.txt
```

3. 환경변수 설정

`.env.example`을 참고하여 `.env`를 구성한다.

예시:

```env
FLASK_APP=app.py
FLASK_ENV=development
FLASK_DEBUG=true
HOST=0.0.0.0
PORT=5001
LOG_LEVEL=INFO
SECRET_KEY=change-this-secret
DATABASE_URL=sqlite:///naver_reporter.db
REQUEST_TIMEOUT=12
MAX_ARTICLES=20
REQUEST_DELAY_SECONDS=0.4
SEARCH_PAGE_SIZE=10
SEARCH_MAX_PAGES=3
USER_AGENT=Mozilla/5.0 (compatible; ReporterAnalyzer/0.1; +prototype)
ENABLE_PLAYWRIGHT_FALLBACK=false
PLAYWRIGHT_TIMEOUT_MS=15000
NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
GOOGLE_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
GEMINI_TIMEOUT=30
```

4. Flask 서버 실행

```bash
python app.py
```

브라우저에서 `http://127.0.0.1:5001` 접속

참고:

- macOS 로컬 기본 DB 경로는 Flask `instance` 디렉터리의 SQLite 파일이다.
- `DATABASE_URL`을 `postgresql+psycopg://...` 형태로 지정하면 PostgreSQL로 전환된다.
- `ENABLE_PLAYWRIGHT_FALLBACK=true`를 켜면 Playwright 브라우저 설치가 추가로 필요하다.

### macOS 로컬 실행 체크

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

선택 사항:

```bash
playwright install chromium
```

위 명령은 `ENABLE_PLAYWRIGHT_FALLBACK=true`일 때만 필요하다.

## Google Cloud Run 배포

### 배포 전 권장 사항

- Cloud Run에서는 컨테이너 재시작 시 로컬 파일이 유지되지 않으므로 `DATABASE_URL`에 Cloud SQL PostgreSQL 연결 문자열을 넣는 것을 권장한다.
- `DATABASE_URL`을 지정하지 않으면 앱은 `/tmp/naver_reporter.db`를 사용한다. 이 경로는 동작 확인용이며 영구 저장소가 아니다.
- Cloud Run은 `PORT` 환경변수를 주입하므로 앱은 자동으로 해당 포트에 바인딩된다.

### 컨테이너 이미지 빌드

프로젝트에는 Cloud Run 배포용 `Dockerfile`이 포함되어 있다.

```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/naver-reporter
```

### Cloud Run 배포 예시

```bash
gcloud run deploy naver-reporter \
  --image gcr.io/PROJECT_ID/naver-reporter \
  --platform managed \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --set-env-vars SECRET_KEY=change-this-secret,LOG_LEVEL=INFO \
  --set-secrets GOOGLE_API_KEY=GOOGLE_API_KEY:latest
```

PostgreSQL 사용 예시:

```bash
gcloud run deploy naver-reporter \
  --image gcr.io/PROJECT_ID/naver-reporter \
  --platform managed \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --set-env-vars SECRET_KEY=change-this-secret,DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
```

### Health Check

- 헬스 엔드포인트: `/healthz`
- JSON API 엔드포인트: `/api/v1/analyze`

## API 호출 예시

### HTML 폼 사용

- 메인 화면에서 언론사명, 기자명, 시작일, 종료일, limit 입력 후 분석 실행

### JSON API 사용

```bash
curl -X POST http://127.0.0.1:5001/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d @sample_request.json
```

응답 예시:

```json
{
  "run_id": 1,
  "reporter": {
    "office_name": "연합뉴스",
    "reporter_name": "김지수",
    "reporter_page_url": "https://media.naver.com/journalist/001/12345"
  },
  "article_count": 14,
  "analysis": {
    "top_keywords": [
      ["정부", 8],
      ["서울", 6]
    ],
    "title_patterns": {
      "question_style": 1,
      "quote_style": 3,
      "bracket_style": 2,
      "average_length": 27.1
    }
  }
}
```

## 설계 흐름 설명

1. `search.py`
   `"{언론사명} {기자명} 기자"` 및 보조 검색어로 네이버 뉴스 검색 결과를 조회한다.
2. `article.py`
   각 기사 본문을 파싱하여 제목, 본문, 언론사, 기자명, 발행일, 기자 링크를 추출하고 검증한다.
3. `collector.py`
   검증 기사에서 대표 기자 페이지 URL을 선정하고, 없으면 officeId 기반 fallback 후보를 시도한다.
4. `reporter.py`
   기자 페이지 기사 목록을 페이지네이션으로 수집한다.
5. `collector.py`
   기자 페이지 기사를 다시 본문 검증하여 오탐을 제거한다.
6. `analysis.py`
   최종 기사 집합을 대상으로 간단한 분석을 수행한다.
7. `models.py`
   reporter, article, analysis run 저장과 재사용을 담당한다.

## 한계점

- 네이버 뉴스 HTML 구조가 바뀌면 selector 보정이 필요하다.
- 기자 페이지 DOM 구조와 무한 스크롤 동작은 매체별/시점별로 달라질 수 있다.
- 현재 한국어 분석은 경량 토큰화 기반이라 조사 분리, 복합명사 처리 정확도가 제한적이다.
- 일부 기사 본문/기자 정보는 자바스크립트 렌더링이 필요할 수 있어 Playwright fallback이 필요하다.
- robots.txt, 서비스 이용약관, 언론사 정책에 따라 수집 가능 범위가 달라질 수 있다.

## 법적/정책적 주의사항

- 이 코드는 프로토타입 예시이며 실제 서비스 운영 전 반드시 법률 자문과 정책 검토가 필요하다.
- `robots.txt`, 네이버 및 언론사 이용약관, API 정책, 저작권, 개인정보, 서비스 부하 기준을 확인해야 한다.
- 과도한 요청을 피하기 위해 timeout, retry, throttling, dedupe를 적용했지만 운영 환경에서는 추가 rate limit이 필요하다.
- 수집 대상 사이트 정책이 변경되면 즉시 중단하거나 수집 방식을 조정해야 한다.

## 향후 개선 아이디어

- KoNLPy, Kiwi 기반 형태소 분석
- SentenceTransformer 또는 임베딩 기반 기사 군집화
- LLM 요약 및 논조 분석
- Celery/RQ 기반 비동기 수집
- 기자별 증분 수집 스케줄러
- 관리자용 수집 상태 대시보드
