# 네이버 기자 분석 웹앱 개발 프롬프트

## 1. 개발 목표

포스코 홍보 담당자가 **언론사명과 기자명**을 입력하면 네이버 뉴스 검색 결과에서 해당 기자의 최신 기사 흐름을 수집하고, 포스코그룹 관련 기사 및 최신 공개 이슈를 함께 분석해 **미팅용 토킹 포인트와 대화 전략**을 자동 생성하는 Flask 웹 애플리케이션을 개발한다.

현재 모듈은 `proj1`이며, 통합 Flask 앱에서는 `/proj1` 경로로 접근하고 단독 실행도 가능해야 한다.

---

## 2. 기술 스택

- 백엔드: Python + Flask
- 앱 구조: Flask Blueprint 기반 모듈 구조
- 크롤링: Playwright Chromium Headless + Requests fallback + BeautifulSoup4
- AI 분석: OpenAI Responses API
- 기본 모델: `.env`의 `OPENAI_MODEL`, 기본값 `gpt-5.5`
- 웹 검색 보강: OpenAI Responses API의 `web_search` 도구
- 프론트엔드: Bootstrap 5 + 커스텀 CSS
- 테마: 다크/화이트 토글 지원
- 반응형: PC + 모바일 지원
- 실행 포트: `.env`의 `FLASK_PORT`, 기본값 `5001`

---

## 3. `.env` 설정

각 프로젝트 폴더가 아니라 **프로젝트 루트(`pr/.env`)의 기존 `.env` 파일**을 사용한다.

```env
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=change-this-secret

OPENAI_API_KEY=<키값>
OPENAI_MODEL=gpt-5.5
OPENAI_FALLBACK_MODEL=gpt-4o-mini

OPENAI_WEB_SEARCH_TOOL=web_search
OPENAI_WEB_SEARCH_TOOL_CHOICE=required
OPENAI_WEB_SEARCH_MODEL=
OPENAI_WEB_SEARCH_FALLBACK_MODEL=
OPENAI_WEB_SEARCH_CONTEXT_SIZE=

REQUEST_TIMEOUT=12
MIN_LATEST_ARTICLES=20
MAX_ARTICLES=20
TARGET_POSCO_ARTICLES=5
MAX_SCAN_ARTICLES=150
MAX_RESULT_SCROLLS=15
MAX_REQUEST_PAGES=8
POSCO_LOOKBACK_MONTHS=1
NAVER_GOTO_RETRIES=4

PLAYWRIGHT_HEADLESS=true
PLAYWRIGHT_LOCALE=ko-KR
PLAYWRIGHT_VIEWPORT_WIDTH=1280
PLAYWRIGHT_VIEWPORT_HEIGHT=800

FLASK_HOST=0.0.0.0
FLASK_PORT=5001
FLASK_DEBUG=false

ADMIN_ID=admin
ADMIN_PASSWORD=admin1234
USER_ID=user
USER_PASSWORD=user1234
SESSION_HOURS=8
SESSION_COOKIE_SECURE=false
```

필수값은 `OPENAI_API_KEY`다. `OPENAI_MODEL`이 없으면 `gpt-5.5`를 사용하고, 1차 호출 실패 시 `OPENAI_FALLBACK_MODEL` 또는 `gpt-4o-mini`로 fallback한다.

---

## 4. 실제 프로젝트 구조

통합 앱과 모듈 앱이 함께 동작하는 구조로 작성한다.

```text
pr/
├── app.py
├── auth.py
├── requirements.txt
├── .env
├── templates/
│   ├── login.html
│   ├── index.html
│   └── 403.html
├── static/
│   ├── css/
│   │   ├── shared.css
│   │   └── theme-toggle.css
│   └── js/
│       └── theme-toggle.js
└── proj1/
    ├── app.py
    ├── README.md
    ├── requirements.txt
    ├── prompt.md
    ├── templates/
    │   └── proj1/
    │       ├── index.html
    │       ├── progress.html
    │       ├── result.html
    │       └── _article.html
    └── static/
        └── style.css
```

`proj1/app.py`는 별도 `utils/` 폴더 없이 크롤링, 분석, 라우팅을 한 파일에 포함한다. 통합 앱에서는 `from proj1.app import bp as proj1_bp`로 등록한다.

---

## 5. 통합 앱과 인증 구조

루트 `app.py`는 다음 역할을 수행한다.

- `.env` 로드
- `auth_bp` 등록
- `proj1`, `proj2`, `proj3` Blueprint 등록
- `/proj1`, `/proj2`, `/proj3` 경로 제공
- 로그인하지 않은 사용자의 모든 내부 페이지 접근을 `/login`으로 리다이렉트
- 루트 `/`에서는 프로젝트 허브 화면 제공

`auth.py`는 다음 기능을 제공한다.

- `ADMIN_ID`, `ADMIN_PASSWORD`, `USER_ID`, `USER_PASSWORD` 기반 로그인
- 세션 기반 사용자 상태 관리
- `login_required`, `admin_required`
- 로그아웃

`proj1/app.py`는 단독 실행도 지원한다.

```python
def create_standalone_app() -> Flask:
    standalone = Flask(__name__)
    standalone.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-secret")
    standalone.register_blueprint(bp)
    return standalone
```

---

## 6. 사용자 입력 화면

메인 화면은 `proj1/templates/proj1/index.html`에서 구현한다.

입력 항목은 다음 2개다.

- 언론사명
- 기자명

화면 요구사항:

- Bootstrap 5 기반 검색 폼
- POSCO PR Intelligence 톤의 히어로 화면
- 언론사명 자동완성
- `media_names`는 서버의 `OFFICE_CODES`를 정렬해 전달
- 오류가 있으면 검색 폼 상단에 Bootstrap alert 표시
- 다크/화이트 테마 토글 표시
- 모바일 반응형 지원

언론사 자동완성은 공백을 제거하고 소문자로 비교해, 입력값으로 시작하는 첫 번째 언론사명을 제안한다. `Tab` 또는 `Enter`로 제안을 수락할 수 있어야 한다.

---

## 7. 언론사 코드 로딩 방식

언론사 코드는 `proj1/app.py`에서 `load_office_codes()`로 로드한다.

기본 fallback 매핑은 다음 값을 포함한다.

```python
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
```

그 외 언론사 코드는 `proj1/prompt.md`의 `언론사명(4자리코드)` 형식을 정규식으로 파싱해 로드한다.

```python
matches = re.findall(r"([^,\n()]+)\((\d{4})\)", text)
```

주의사항:

- 현재 구현은 네이버 기자홈의 3자리 `officeId`가 아니라 네이버 뉴스 검색의 4자리 `news_office_checked` 값을 사용한다.
- `proj1/prompt.md`가 있으면 해당 파일이 언론사 코드의 단일 소스 역할을 한다.
- `http`, `URL`, `키값`, `선택시` 등 설명 문구가 섞인 잘못된 캡처는 제외한다.
- 사용자가 입력한 언론사명은 정확 일치, 대소문자 무시 일치, 포함 일치 순서로 찾는다.
- 매체를 찾지 못하면 지원 언론사 예시 목록을 포함한 오류 메시지를 반환한다.

---

## 8. 네이버 검색 URL 구성

현재 구현은 네이버 기자홈 직접 접근이 아니라 네이버 뉴스 검색 탭의 언론사 필터와 기자명 옵션을 사용한다.

### 언론사 필터 URL

```text
https://search.naver.com/search.naver?
ssc=tab.news.all
&where=news
&sm=tab_opt
&sort=1
&photo=0
&field=0
&pd=-1
&query=
&mynews=1
&office_type=2
&office_section_code=3
&news_office_checked={office_code}
&nso=
&is_sug_officeid=0
&office_category=0
&service_area=0
```

### 기자명 검색 URL

```text
field=2
query={reporter_name}
news_office_checked={office_code}
```

### 언론사 내 키워드 fallback URL

```text
field=0
query={reporter_name}
news_office_checked={office_code}
```

기본 정렬은 최신순(`sort=1`), 기간은 전체(`pd=-1`)다.

---

## 9. 크롤링 흐름

크롤링 진입 함수는 `crawl_naver_news(media_name, reporter_name, progress)`다.

처리 순서:

1. `find_office_code()`로 언론사 코드 확인
2. 네이버 검색 언론사 필터 URL 생성
3. Playwright Chromium 실행
4. `goto_naver_with_retries()`로 네이버 검색 페이지 진입
5. 옵션 패널을 열고 기자명 필터 적용
6. 검색 결과를 스크롤하면서 기사 링크 수집
7. 최신 기사와 포스코 관련 기사 후보를 선정
8. 기사 원문 수집
9. 결과 dict 반환

브라우저 환경:

- headless 여부: `PLAYWRIGHT_HEADLESS`, 기본 `true`
- locale: `PLAYWRIGHT_LOCALE`, 기본 `ko-KR`
- viewport: `PLAYWRIGHT_VIEWPORT_WIDTH`, `PLAYWRIGHT_VIEWPORT_HEIGHT`
- User-Agent는 Chrome 계열 문자열 사용

네이버 접속이 일시적으로 실패하면 다음 오류를 재시도 대상으로 본다.

- `ERR_NAME_NOT_RESOLVED`
- `ERR_CONNECTION_RESET`
- `ERR_CONNECTION_CLOSED`
- `ERR_CONNECTION_TIMED_OUT`
- `ERR_TIMED_OUT`
- `net::ERR`

재시도 횟수는 `NAVER_GOTO_RETRIES`, 기본 4회다.

---

## 10. 기자명 옵션 적용

`apply_reporter_option(page, reporter_name, progress)`는 네이버 검색 옵션 UI를 조작한다.

옵션 버튼 후보:

```python
[
    "a:has-text('옵션')",
    "button:has-text('옵션')",
    "#snb .btn_option",
    ".btn_option",
]
```

기자명 입력란:

```text
#news_input_reporter_name
```

적용 방식:

1. 옵션 버튼 클릭 시도
2. 기자명 입력란에 값 주입
3. `news_submit_reporter_option()` 호출
4. 실패 시 `#news_form`의 `field`를 `2`로 바꾸고 submit
5. 적용 후 URL에 `field=2`가 포함되지 않으면 오류 처리

---

## 11. 기사 목록 추출

검색 결과 HTML에서 기사 후보를 추출하는 함수는 `extract_articles_from_html()`이다.

탐색 대상:

```text
a.news_tit
a.ZndmRRvmX99p7vSVdwfb
a[href]
```

기사 제목 링크 판단 조건:

- 제목이 비어 있지 않을 것
- `네이버뉴스`, `뉴스`, `언론사 선정` 같은 보조 링크가 아닐 것
- 제목 길이가 6자 이상일 것
- `news_tit` 클래스가 있으면 우선 인정
- 네이버 뉴스 기사 URL이면 인정
- 네이버의 생성형 클래스 또는 현재 뉴스 카드 구조 신호가 있으면 인정

기사 URL 필터:

- `search.naver.com`, `media.naver.com`, `www.naver.com`, `naver.com`, `keep.naver.com`은 제외
- `news.naver.com`은 `/mnews/article/` 또는 `/article/` 경로만 허용
- 일반 외부 언론사 URL도 기사 URL로 허용
- `channelPromotion` URL은 제외

날짜 추출 패턴:

```text
YYYY.MM.DD. HH:MM
YYYY.MM.DD.
YYYY-MM-DD HH:MM
YYYY-MM-DD
N분 전
N시간 전
N일 전
N주 전
N개월 전
```

중복 제거 기준은 기사 URL, URL이 없으면 제목이다.

---

## 12. 스크롤 및 수집 중단 조건

Playwright 방식의 기사 목록 수집은 최대 `MAX_RESULT_SCROLLS`회 수행한다. 기본값은 15회다.

각 라운드에서 다음을 수행한다.

1. 현재 HTML에서 기사 추출
2. 최신 기사 수가 충분한지 확인
3. 포스코 기사 후보가 충분한지 확인
4. 최근 1개월 범위를 벗어난 기사가 나타났는지 확인
5. 페이지를 아래로 스크롤

중단 조건:

- 최신 기사 수가 `max(MAX_ARTICLES, MIN_LATEST_ARTICLES)` 이상이고, 포스코 후보가 `TARGET_POSCO_ARTICLES` 이상이면 중단
- 최신 기사 수가 충분하고, 포스코 검색 기간 창을 넘어간 기사 날짜가 확인되면 중단
- 기사 수가 6회 이상 늘지 않고 최신 기사 수가 최소 기준 이상이면 중단

기본 수집량:

- `MIN_LATEST_ARTICLES`: 20
- `MAX_ARTICLES`: 없으면 20
- `TARGET_POSCO_ARTICLES`: 5
- `MAX_SCAN_ARTICLES`: 150
- `POSCO_LOOKBACK_MONTHS`: 1

---

## 13. Requests fallback

브라우저 방식이 네이버 연결 오류로 실패하거나 기자명 옵션 결과가 비어 있으면 Requests 기반 수집으로 보완한다.

`crawl_naver_news_requests()` 동작:

- `requests.Session()` 사용
- Chrome 계열 User-Agent와 한국어 Accept-Language 설정
- 페이지당 `start=1, 11, 21...` 방식으로 페이지 이동
- 최대 `MAX_REQUEST_PAGES`, 기본 8페이지 조회
- 403 또는 429가 발생했더라도 이미 수집한 기사가 있으면 그 범위에서 진행
- `field=2` 기자명 검색 결과가 비어 있으면 언론사 내 일반 키워드 검색(`field=0`)으로 fallback

Requests fallback에서도 기사 원문 수집과 날짜 보정은 동일하게 수행한다.

---

## 14. 기사 원문 수집

원문 수집 함수:

- Playwright 방식: `fetch_article_body(page, url)`
- Requests 방식: `fetch_article_body_requests(session, url)`

본문 선택자 우선순위:

```text
div#dic_area
div.newsct_article
div#articleBodyContents
article
```

선택자로 본문을 찾지 못하면 모든 `<p>` 태그 텍스트를 합쳐 fallback한다.

본문 정리:

- 연속 공백 제거
- `구독.*?추천`
- `무단전재.*?금지`
- `Copyright.*`
- `기자 페이지`
- 최대 8000자까지 보관

날짜는 다음 메타/표시 요소에서 추출한다.

```text
meta[property="article:published_time"]
meta[name="article:published_time"]
meta[property="og:article:published_time"]
meta[name="pubdate"]
meta[name="publish-date"]
meta[name="date"]
meta[itemprop="datePublished"]
span.media_end_head_info_datestamp_time
span._ARTICLE_DATE_TIME
time
.date
.article_date
.viewDate
.view_date
.news_date
.write_date
.byline
```

본문 또는 날짜 수집에 실패해도 제목, URL, 요약만으로 분석을 계속 진행한다.

---

## 15. 포스코 관련 기사 판별

포스코 관련 기사 판별 키워드는 현재 코드 기준으로 다음과 같다.

```python
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
```

판별 방식:

- 제목에 키워드가 포함되면 포스코 기사로 판단
- 제목에는 없지만 요약에 같은 키워드가 2회 이상 반복되면 포스코 기사로 판단
- 포스코 관련 기사 목록은 최근 `POSCO_LOOKBACK_MONTHS`개월 이내 기사만 포함
- 기본값은 최근 1개월, 최대 5건

원문 상세 수집 대상:

- 최신 기사 목록
- 스캔된 기사 중 포스코 제목/요약 후보

---

## 16. AI 분석 방식

AI 분석은 OpenAI Responses API를 2회 호출한다.

### 공통 호출 방식

`call_openai_json()`:

- `OPENAI_API_KEY` 필수
- `OPENAI_MODEL` 기본 `gpt-5.5`
- 실패 시 `OPENAI_FALLBACK_MODEL` 또는 `gpt-4o-mini` 사용
- system/user prompt를 `input` 배열로 전달
- 응답의 `output_text` 또는 `model_dump()`에서 텍스트 추출
- JSON 코드블록, 앞뒤 설명이 섞여도 JSON object를 찾아 파싱
- 파싱 실패 시 `raw`에 원문 저장

`call_openai_web_search_json()`:

- OpenAI web search tool 사용
- 기본 도구명은 `web_search`
- 기본 tool choice는 `required`
- `OPENAI_WEB_SEARCH_CONTEXT_SIZE`가 있으면 도구 옵션에 반영
- 웹 검색 호출 메타데이터와 citation은 `_web_search`에 저장 가능

---

## 17. 1차 분석: 종합 분석

함수: `analyze_general()`

입력 데이터:

- 언론사명
- 기자명
- 최신 기사 약 20건
- 최근 1개월 내 포스코그룹 관련 기사 최대 5건

출력 JSON 스키마:

```json
{
  "interest_areas": [
    {
      "name": "분야",
      "evidence": "근거"
    }
  ],
  "tone": {
    "stance": "비판적|중립적|우호적|혼합",
    "summary": "전체 요약",
    "features": ["특징"]
  },
  "keywords": [
    {
      "word": "키워드",
      "frequency": "높음|중간|낮음"
    }
  ]
}
```

프롬프트 요구사항:

- 한국어 JSON만 반환
- 관심 주제는 정확히 5개
- 관심 주제 `name`은 12~20글자 내외의 설명형 제목
- `evidence`는 2문장 이내
- `tone.summary`는 관찰자 관점의 분석문
- `tone.summary`에는 최근 관심 이슈, 기사 결, 보도 시각, 보도 흐름이 드러나야 함
- 포스코 관련 내용이 있으면 `tone.features` 마지막 항목에 별도 정리
- `tone.features`는 주요 내용 3개 내외
- 키워드는 정확히 5개
- 상위 2개 키워드는 `frequency`를 `높음`, 나머지는 `중간`으로 작성

---

## 18. 2차 분석: 토킹 포인트

함수: `analyze_talking_points()`

입력 데이터:

- 언론사명
- 기자명
- 최신 기사
- 포스코 관련 기사
- 1차 종합 분석 결과

특징:

- OpenAI web search tool을 필수로 사용한다.
- 포스코 관련 수집 기사가 적어도 기자 관심사와 맞닿는 최신 포스코그룹 공개 이슈를 웹 검색으로 보강한다.
- 오래된 경영이념, 슬로건, 과거 회장 체제 메시지는 최근 1년 내 현재 메시지로 확인되지 않으면 핵심 근거로 쓰지 않는다.
- 포스코, 포스코인터내셔널, 포스코이앤씨, 포스코퓨처엠, 포스코DX 등 사업회사별 맥락을 가능한 한 구분한다.
- 기사 제목/내용에 칼럼, 논설, 주필, 데스크, 사설, 시론 성격이 강하면 데스크·논설형 인물로 간주하고 C레벨 대담용 거시 의제로 구성한다.

출력 JSON 스키마:

```json
{
  "meeting_strategy": "토킹 포인트 개요",
  "talking_points": [
    {
      "title": "단계명과 목적",
      "scenario": "1인칭 토킹 시나리오",
      "reason": "카드의 역할"
    }
  ]
}
```

프롬프트 요구사항:

- `meeting_strategy`는 약 3줄, 길어도 4줄 이하
- 기자 관심사 → 포스코그룹 접점 → 기회/리스크 메시지 순서로 구성
- 실행 선언형이 아니라 조언형 문장으로 작성
- `talking_points`는 중요도순 3~5개
- 중복되는 내용이 있으면 5개를 억지로 채우지 않음
- `title`은 짧고 실무적인 제목
- `scenario`는 포스코 커뮤니케이션실 15년 경력의 언론 대응 관계자가 말하는 느낌의 1인칭 대화문
- `scenario`에는 `기자님`, `기자님께서`, `기자님의` 표현 금지
- `scenario`는 `최근에 쓰신`, `관심을 보이신`, `주목하고 계신`처럼 직접 호칭을 생략한 문장으로 시작
- `scenario`는 `·` 또는 `-`로 시작하는 3~5개 불릿
- `scenario`는 500자 이내
- 가능한 경우 숫자, 기간, 규모, 목표, 투자액, 생산능력, 수주액 등 정량 정보 포함
- `meeting_strategy`와 `talking_points`에는 출처 표기, URL, 마크다운 링크를 넣지 않음

응답 정규화:

- `meeting_strategy`, `strategy`, `overview`, `summary` 중 존재하는 값을 전략으로 사용
- `talking_points`, `key_talking_points`, `key_points`, `points`, `talkingPoint`, `items` 등 다양한 키를 허용
- 문자열 포인트도 카드 형태로 변환
- URL, 마크다운 링크, 괄호 속 URL을 제거

---

## 19. 백그라운드 작업 구조

크롤링과 AI 분석은 오래 걸리므로 백그라운드 스레드로 실행한다.

```python
threading.Thread(target=run_job, args=(job_id, media_name, reporter_name), daemon=True)
```

작업 상태는 메모리 전역 딕셔너리에 저장한다.

```python
jobs: dict[str, dict[str, Any]] = {}
jobs_lock = threading.Lock()
```

작업 상태 필드:

- `status`: queued, running, done, error
- `percent`: 0~100
- `message`: 현재 상태 메시지
- `media_name`
- `reporter_name`
- `log`
- `result`
- `error`
- `traceback`

진행률 기준:

- 3%: 작업 시작
- 8~15%: 언론사 필터 및 기자명 옵션 적용
- 15~40%: 기사 목록 수집
- 42~64%: 기사 원문 수집
- 68%: 종합 분석 요청
- 84%: 토킹 포인트 생성
- 100%: 완료 또는 오류

---

## 20. Flask 라우트

`proj1` Blueprint 라우트:

```text
GET  /                    검색 화면
POST /search              검색 작업 생성
GET  /progress/<job_id>   진행 상황 화면
GET  /api/status/<job_id> 진행 상태 JSON API
GET  /result/<job_id>     분석 결과 화면
```

통합 앱에서는 위 라우트가 `/proj1` prefix 아래에 등록된다.

```text
GET  /proj1
POST /proj1/search
GET  /proj1/progress/<job_id>
GET  /proj1/api/status/<job_id>
GET  /proj1/result/<job_id>
```

API 동작:

- 작업이 없으면 404와 `status: missing`
- 완료되면 `result_url` 포함
- `FLASK_DEBUG=true`일 때만 traceback을 API 응답에 포함

---

## 21. 진행 화면

진행 화면은 `proj1/templates/proj1/progress.html`에서 구현한다.

요구사항:

- 2초 간격으로 `/api/status/<job_id>` polling
- 진행률 숫자와 progress bar 표시
- 단계 표시: 언론사 및 기자 검색 → 기사 수집 → AI 분석
- 완료 시 결과 페이지로 자동 이동
- 오류 시 alert 표시
- 새 검색 링크 제공
- 테마 토글 제공

진행 메시지는 프론트엔드에서 일부 다듬어 표시한다.

- 기사 원문 수집 메시지는 `(현재/전체)` 형식 표시
- 스크롤 메시지는 기사 수 중심으로 표시
- 종합 분석, 토킹 포인트 생성 단계는 별도 메시지로 표시

---

## 22. 결과 화면 구성

결과 화면은 `proj1/templates/proj1/result.html`에서 Bootstrap 탭 4개로 구성한다.

현재 탭 순서:

| 순서 | 탭 | 내용 |
|---|---|---|
| 1 | 종합 분석 | 관심 주제, 기사 분석, 관심 키워드 |
| 2 | 토킹 포인트 | 토킹 포인트 개요, 핵심 토킹 포인트 카드 |
| 3 | 최신 기사 | 수집된 최신 기사 목록, 날짜, 요약, 원문 링크 |
| 4 | 포스코 기사 | 최근 1개월 포스코 관련 기사 최대 5건 |

상단 프로필 영역:

- 기자명
- 언론사명
- 분석 기사 수
- 포스코 기사 수
- 새 검색 버튼
- 네이버 결과 링크
- 테마 토글

종합 분석 탭:

- 관심 주제 최대 5개
- 기사 분석 요약
- 일반 feature와 포스코 feature를 분리 강조
- `[단독]`, `[기획]`, `현장취재`, `르포`, `기자수첩` 등 특수 기사 제목은 별도 박스로 노출
- 관심 키워드 5개를 랭킹 UI로 표시

토킹 포인트 탭:

- `meeting_strategy`를 토킹 포인트 개요로 표시
- `talking_points`를 카드 목록으로 표시
- 각 카드에는 번호, 제목, 시나리오, 활용 이유를 표시
- 제목과 이유는 템플릿 필터로 불필요한 접두어와 URL을 제거

최신 기사/포스코 기사 탭:

- `_article.html` partial 사용
- 제목, 날짜, 언론사, 요약, 원문 링크 표시
- 날짜가 없으면 `날짜 미확인`

---

## 23. 스타일 요구사항

`proj1/static/style.css`는 다음 UI 톤을 구현한다.

- 메인 검색 화면: 전체 화면 히어로 배경 이미지 + 중앙 검색 패널
- 결과 화면: 넓은 데스크톱 레이아웃, 카드형 분석 패널
- Bootstrap 기본 버튼 색상은 포스코 계열 블루로 오버라이드
- 카드 radius는 8~12px 범위
- 결과 탭은 선명한 활성 상태 표시
- 토킹 포인트 카드는 번호 배지와 본문 구분
- 모바일에서 결과 상단, 탭, 카드 그리드가 단일 컬럼으로 자연스럽게 접혀야 함
- 공통 테마 토글 CSS는 루트 `static/css/theme-toggle.css`를 사용
- 테마 토글 JS는 루트 `static/js/theme-toggle.js`를 사용

---

## 24. 예외 처리 및 로그

예외 처리 요구사항:

- 미지원 언론사: 지원 언론사 예시와 함께 오류
- 네이버 옵션 UI 변경: 기자명 입력란 또는 옵션 적용 실패 메시지
- 네이버 연결 불안정: 재시도 후 Requests fallback
- 검색 결과 없음: 언론사명과 기자명 확인 요청
- 기사 원문 수집 실패: 본문 없이 제목/날짜/URL만으로 계속 진행
- OpenAI API 키 없음: `.env에 OPENAI_API_KEY가 없습니다.`
- Windows 권한 오류: 브라우저 실행 권한 오류 메시지

로그 파일:

```text
proj1/last_crawler_error.log
proj1/last_job_error.log
```

오류 발생 시 예외 타입, 메시지, traceback을 파일에 기록한다.

---

## 25. 실행 방법

### 의존성 설치

루트 통합 실행 기준:

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

`proj1`만 별도 의존성을 설치할 경우:

```bash
python3 -m pip install -r proj1/requirements.txt
python3 -m playwright install chromium
```

### 통합 앱 실행

```bash
cd /path/to/pr
python3 app.py
```

브라우저:

```text
http://127.0.0.1:5001
```

로그인 후 `/proj1`로 이동한다.

### proj1 단독 실행

```bash
cd /path/to/pr/proj1
python3 -B app.py
```

브라우저:

```text
http://127.0.0.1:5001
```

단독 실행 시에는 통합 앱의 로그인 보호 없이 `proj1` 검색 화면이 열린다.

---

## 26. 핵심 개발 조건

- 코드는 `proj1/app.py`의 단일 파일 구조를 유지한다.
- `proj1`은 통합 앱의 Blueprint로 등록 가능해야 한다.
- 동시에 단독 실행도 가능해야 한다.
- 루트 `.env`를 우선 사용한다.
- AI 분석은 OpenAI Responses API를 사용한다.
- 토킹 포인트 생성은 OpenAI web search tool을 사용한다.
- 네이버 기자홈 3자리 `officeId` 방식이 아니라 네이버 검색의 4자리 `news_office_checked` 방식을 사용한다.
- 언론사 코드는 `proj1/prompt.md`에서 동적으로 로드한다.
- 네이버 검색 옵션 UI를 조작해 기자명 필터를 적용한다.
- 브라우저 방식 실패 시 Requests 방식으로 fallback한다.
- 기사 본문 수집 실패 시에도 분석을 계속한다.
- 포스코 관련 기사는 제목 키워드와 요약 반복 키워드로 판단한다.
- 최근 포스코 기사 범위는 기본 최근 1개월이다.
- 진행률은 메모리 `jobs` 딕셔너리와 polling API로 구현한다.
- 결과 화면은 4개 탭으로 구성한다.
- 모바일 반응형과 테마 토글을 지원한다.
- 오류 발생 시 사용자 메시지와 로그 파일을 남긴다.

---

## 27. 최종 요청

위 요구사항에 따라 현재 `proj1` 모듈과 동일한 수준의 Flask 웹 애플리케이션 코드를 작성해줘.

다음 조건을 반드시 만족해줘.

- 루트 통합 앱과 `proj1` 단독 실행을 모두 고려
- `proj1/app.py`에 Blueprint, 크롤링, AI 분석, 라우팅 구현
- `templates/proj1/index.html`, `progress.html`, `result.html`, `_article.html` 포함
- `proj1/static/style.css` 포함
- `proj1/requirements.txt` 포함
- 루트 `.env` 사용
- OpenAI Responses API 연동
- OpenAI web search tool 기반 토킹 포인트 보강
- Playwright 기반 네이버 검색 옵션 조작
- Requests fallback 구현
- BeautifulSoup 기반 기사 목록 및 본문 파싱
- 기사 원문 수집 실패 시 제목 기반 분석 fallback
- 백그라운드 스레드 작업 처리
- 2초 polling 진행률 UI
- Bootstrap 기반 반응형 UI
- 다크/화이트 테마 토글
- 오류 처리와 로그 파일 기록
- 실행 방법과 설치 명령 포함
- 코드 전체를 바로 실행 가능한 수준으로 작성
