# 정부 안전/노동 주요인사 발언 및 중대재해 분석 웹앱 개발 프롬프트

## 1. 프로젝트 개요

정부 주요 인사의 안전·노동 관련 발언과 국내 중대재해 사례를 기간별로 수집하고, SQLite DB에 누적 관리하며, 저장 데이터를 바탕으로 포스코그룹의 경영층 보고용 시사점·대응방안·당사 사고 사과문 및 대응 방향을 생성하는 Flask 웹 애플리케이션을 개발한다.

현재 모듈은 `proj2`이며, 통합 Flask 앱에서는 `/proj2` 경로로 접근하고 단독 실행도 가능해야 한다.

---

## 2. 기술 스택

- 백엔드: Python + Flask
- 앱 구조: Flask Blueprint 기반 모듈 구조
- 데이터베이스: SQLite
- DB 파일: `proj2/instance/safety_labor.db`
- 데이터 수집: OpenAI Responses API `web_search` 도구
- AI 분석: OpenAI Chat Completions API
- 기본 분석 모델: `.env`의 `OPENAI_MODEL`, 기본값 `gpt-5.5`
- 웹 검색 모델: `.env`의 `OPENAI_WEB_SEARCH_MODEL`, 기본값 `gpt-5.5`
- 프론트엔드: Bootstrap 5.3.3 + Bootstrap Icons + 커스텀 CSS/JS
- 테마: 다크/화이트 토글 지원
- 반응형: PC + 모바일 지원
- 통합 실행 포트: `.env`의 `FLASK_PORT`, 기본값 `5001`
- 단독 실행 포트: `.env` 또는 실행 환경의 `PORT`, 기본값 `5001`

---

## 3. `.env` 설정

각 프로젝트 폴더가 아니라 **프로젝트 루트(`pr/.env`)의 기존 `.env` 파일**을 사용한다.

```env
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=change-this-secret

OPENAI_API_KEY=<키값>
OPENAI_MODEL=gpt-4o-mini
OPENAI_WEB_SEARCH_MODEL=gpt-5.5
OPENAI_WEB_SEARCH_CONTEXT_SIZE=medium
OPENAI_SPEECH_SEARCH_FALLBACK_QUERIES=8
OPENAI_SPEECH_SEARCH_FALLBACK_WORKERS=3

FLASK_HOST=0.0.0.0
FLASK_PORT=5001
PORT=5001
SESSION_HOURS=8
SESSION_COOKIE_SECURE=false

ADMIN_ID=admin
ADMIN_PASSWORD=admin1234
USER_ID=user
USER_PASSWORD=user1234
```

필수값은 `OPENAI_API_KEY`다. 기존 초안과 달리 현재 구현은 Gemini 또는 Google Search Grounding을 사용하지 않는다.

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
└── proj2/
    ├── app.py
    ├── README.md
    ├── requirements.txt
    ├── prompt.md
    ├── instance/
    │   └── safety_labor.db
    ├── templates/
    │   └── proj2/
    │       └── index.html
    └── static/
        ├── css/
        │   └── app.css
        └── js/
            └── app.js
```

`proj2/app.py`는 별도 service/utils 폴더 없이 DB, 수집, 분석, CSV, 라우팅을 한 파일에 포함한다. 통합 앱에서는 `from proj2.app import bp as proj2_bp, init_db as init_proj2_db`로 등록하고, 앱 생성 시 `init_proj2_db()`를 호출한다.

---

## 5. 통합 앱과 인증 구조

루트 `app.py`는 다음 역할을 수행한다.

- 프로젝트 루트 `.env` 로드
- `auth_bp` 등록
- `proj1`, `proj2`, `proj3` Blueprint 등록
- `proj2`를 `/proj2` prefix로 등록
- 비로그인 사용자의 모든 내부 페이지 접근을 `/login`으로 리다이렉트
- `proj2` DB 스키마 초기화

`proj2` 라우트 권한:

- 일반 사용자 로그인 필요: 조회, 데이터검색, CSV 다운로드
- 관리자 권한 필요: 데이터 추출, 저장, 수정, 삭제, CSV 업로드, 종합분석 생성, 기사 링크 보정, 당사사고 대응 생성/저장/수정/삭제

단독 실행 시 `auth.py` import가 실패하면 `login_required`, `admin_required`를 빈 데코레이터로 대체해 인증 없이 동작하도록 한다.

---

## 6. SQLite 스키마

`init_db()`는 다음 테이블을 생성한다.

### speeches

주요인사 발언 저장 테이블.

```sql
CREATE TABLE IF NOT EXISTS speeches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    speech_date TEXT,
    actor TEXT,
    organization TEXT,
    venue TEXT,
    quote TEXT,
    keywords TEXT,
    source_title TEXT,
    source_url TEXT,
    source_name TEXT,
    raw_payload TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### incidents

중대재해 사례 저장 테이블.

```sql
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT,
    accident_date TEXT,
    accident_summary TEXT,
    external_response TEXT,
    implication TEXT,
    apology_text TEXT,
    source_title TEXT,
    source_url TEXT,
    source_name TEXT,
    raw_payload TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### analysis_reports

종합분석 저장 테이블.

```sql
CREATE TABLE IF NOT EXISTS analysis_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

### company_accidents

당사 사고 대응 기록 저장 테이블.

```sql
CREATE TABLE IF NOT EXISTS company_accidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_description TEXT NOT NULL,
    apology_text TEXT,
    response_direction TEXT,
    context_snapshot TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### collection_runs

데이터 수집 이력 저장 테이블.

```sql
CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_on TEXT NOT NULL,
    ended_on TEXT NOT NULL,
    prompt_type TEXT NOT NULL,
    item_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    error_message TEXT,
    raw_response TEXT,
    created_at TEXT NOT NULL
);
```

인덱스:

- `idx_speeches_date`
- `idx_incidents_date`
- `idx_speeches_source_url`
- `idx_incidents_source_url`

---

## 7. 화면 구성

`proj2/templates/proj2/index.html`은 단일 페이지 탭 UI다.

상단:

- 제목: `정부 안전/노동 주요 발언 및 중대재해 분석`
- 설명: `OpenAI web_search 수집, OpenAI 종합 분석, SQLite 누적 관리`
- 다크/화이트 테마 토글
- Bootstrap alert 기반 flash 메시지

탭 목록:

1. 종합분석
2. 주요인사발언
3. 중대재해사례
4. 데이터검색
5. 당사사고 대응방향

현재 활성 탭은 서버가 넘기는 `active_tab` 값과 URL hash를 함께 반영한다.

---

## 8. OpenAI web_search 수집 공통 로직

웹 검색 수집은 `call_openai_web_search(prompt)`에서 수행한다.

동작:

- `OPENAI_API_KEY` 확인
- `OpenAI(api_key=...)` 생성
- `client.responses.create()` 호출
- 모델: `OPENAI_WEB_SEARCH_MODEL`, 기본 `gpt-4.1-mini`
- tool: `{"type": "web_search", "search_context_size": ...}`
- `tool_choice="required"`
- `include=["web_search_call.action.sources"]`
- 응답 텍스트와 web search 출처를 함께 반환

`OPENAI_WEB_SEARCH_CONTEXT_SIZE`는 `low`, `medium`, `high`만 허용하고 그 외 값은 `medium`으로 처리한다.

응답 텍스트 추출:

- `response.output_text` 우선
- 없으면 `response.output`의 message content를 순회해 text 추출

출처 추출:

- message annotation의 `url_citation`
- `web_search_call.action.sources`
- 중복 URL 제거
- 유효한 http/https URL만 저장

---

## 9. URL 검증과 원문 링크 보정

현재 구현은 기사 URL 정확도를 중요하게 처리한다.

유효 URL 조건:

- scheme이 `http` 또는 `https`
- netloc 존재
- legacy grounding redirect URL이 아닐 것

legacy grounding redirect URL:

```text
vertexaisearch.cloud.google.com/grounding-api-redirect/
```

처리 방식:

- `resolve_redirect_url()`로 redirect URL의 최종 URL을 확인
- YouTube URL은 oEmbed API로 재생 가능한지 검증
- placeholder URL(`example.com`, `example.org`, `example.net`, `localhost`) 제외
- URL 경로에 포함된 날짜가 수집 기간과 충돌하면 제외
- 출처 URL이 없거나 legacy redirect이면 `lookup_exact_article_source()`로 OpenAI web_search를 다시 호출해 정확한 원문 URL을 찾는다.

관리 기능:

- 종합분석 탭의 `기사 링크 보정` 버튼은 `repair_all_source_links()`를 실행한다.
- `speeches`, `incidents` 테이블의 빈 URL 또는 legacy redirect URL을 보정한다.
- 보정 성공/실패 건수를 flash 메시지로 표시한다.

---

## 10. JSON 파싱 규칙

OpenAI 응답은 JSON만 기대하지만, 코드블록이나 설명 문장이 섞일 수 있으므로 다음 함수를 사용한다.

- `extract_json_array(text)`
- `parse_json_object(text)`

처리 규칙:

- ```json 코드블록 제거
- 배열(`[...]`) 또는 객체(`{...}`) 부분을 정규식으로 추출
- list이면 dict 항목만 반환
- dict이면 `items`, `speeches`, `incidents`, `data`, `results` 키의 list를 우선 반환
- 객체만 있을 경우 단일 원소 배열로 반환
- 파싱 실패 시 오류 발생

---

## 11. 주요인사발언 수집

수집 대상:

- 이재명 대통령
- 김영훈 노동장관
- 김영훈 고용노동부 장관

주제:

- 산업안전
- 중대재해
- 산재
- 안전보건
- 노동정책
- 노사관계
- 파업
- 교섭
- 임금
- 고용
- 비정규직

사용자는 시작일과 종료일을 선택한다. 날짜는 `YYYY-MM-DD`로 검증하고, 시작일이 종료일보다 늦으면 오류 처리한다.

### 검색어 생성

`speech_search_query_labels()`:

- 기간이 10일 이하이면 날짜 단위 라벨 생성
- 기간이 길면 월 단위 라벨 생성
- 월 라벨은 최대 8개

`speech_search_queries()`:

각 라벨별로 다음 검색어를 생성한다.

```text
이재명 대통령 {label} 산업안전 중대재해 산재 안전보건 발언
이재명 대통령 {label} 노동정책 노동자 노동시간 고용 발언
김영훈 노동장관 {label} 산업안전 중대재해 산재 안전보건 발언
김영훈 노동장관 {label} 노동 노사 파업 교섭 임금 발언
김영훈 고용노동부 장관 {label} 노동 정책 보도자료
```

최대 60개 검색어만 사용한다.

### 주요 프롬프트 요구사항

OpenAI web_search로 한국 웹, 정부 보도자료, 유튜브, X, 페이스북 등 공개 게시물을 검색한다.

반환 형식은 JSON 배열만 허용한다.

각 객체 필드:

- `speech_date`: YYYY-MM-DD
- `actor`: 발언자
- `organization`: 직책/기관
- `venue`: 장소, 회의, 보도자료, 언론사 또는 플랫폼
- `quote`: 핵심 발언 요약
- `keywords`: 키워드 배열
- `source_title`: 기사/게시물 제목
- `source_url`: 실제 원문 URL
- `source_name`: 언론사 또는 플랫폼명

제외 조건:

- 중복 source_url
- 단순 재전송 기사
- 안전·노동과 무관한 일반 정치 발언
- 출처 URL이 없는 항목
- 수집 기간 밖 항목
- 이재명/김영훈이 아닌 인물

직접 인용이 없으면 인용문을 만들지 말고 보도된 발언을 짧게 요약한다.

---

## 12. 주요인사발언 fallback 검색

주요인사발언 수집 결과가 0건이면 fallback 검색을 수행한다.

환경변수:

- `OPENAI_SPEECH_SEARCH_FALLBACK_QUERIES`, 기본 8
- `OPENAI_SPEECH_SEARCH_FALLBACK_WORKERS`, 기본 3

fallback 검색어 템플릿:

```text
김영훈 노동장관 {label} 파업
김영훈 노동장관 {label} 삼성전자
김영훈 고용노동부 장관 {label} 중대재해 산재
이재명 대통령 {label} 노동
이재명 대통령 {label} 중대재해 산재
김영훈 노동장관 {label} 노사 교섭 임금
```

ThreadPoolExecutor로 병렬 검색하고, 결과는 `dedupe_items()`로 중복 제거한다.

---

## 13. 중대재해사례 수집

사용자는 시작일과 종료일을 선택한다.

OpenAI web_search 프롬프트 원문 의도:

```text
해당 기간에 일어난 중대재해 사고 관련해서도 모두 찾아줘.
```

반환 형식은 JSON 배열만 허용한다. 1개의 중대재해 사고를 1개 객체로 만든다.

각 객체 필드:

- `company_name`: 회사명 또는 사업장명
- `accident_date`: YYYY-MM-DD, 불명확하면 보도일
- `accident_summary`: 사고내용
- `external_response`: 회사/정부/노동부/수사기관의 대외대응
- `implication`: 안전·노동 정책상 시사점
- `source_title`: 대표 기사 제목
- `source_url`: 대표 출처 URL
- `source_name`: 대표 언론사/플랫폼명

중대재해 사례 저장 시 `reaction` 또는 `반응`이 포함된 임의 키는 제거한다.

---

## 14. 데이터 저장과 중복 처리

수집 결과는 바로 DB에 저장하지 않고, 먼저 미리보기 상태로 화면에 표시한다. 담당자가 확인 후 저장 버튼을 누르면 DB에 저장한다.

`save_collection_payload()`는 다음 섹션을 저장한다.

- `speeches` → `insert_speech`
- `incidents` → `insert_incident`

중복 기준:

### speeches

- source_url이 있으면 source_url 중복 우선
- source_url이 없으면 `speech_date + actor + quote` 조합으로 중복 판단

### incidents

- source_url이 있으면 source_url 중복 우선
- source_url이 없으면 `company_name + accident_date + accident_summary` 조합으로 중복 판단

저장 후 `collection_runs`에 다음을 기록한다.

- 수집 시작일
- 수집 종료일
- 구분명
- 신규 저장 건수
- 중복 제외 건수
- 상태
- 오류 메시지
- raw_response
- 생성 시각

---

## 15. CSV 업로드/다운로드

주요인사발언과 중대재해사례는 각각 CSV 업로드와 다운로드를 지원한다.

### CSV 인코딩

업로드 파일은 다음 순서로 디코딩한다.

1. `utf-8-sig`
2. `utf-8`
3. `cp949`

읽을 수 없으면 `UTF-8 또는 CP949 CSV로 저장해 주세요.` 오류를 표시한다.

### 주요인사발언 CSV 필드 alias

```python
SPEECH_CSV_MAPPING = {
    "speech_date": ("speech_date", "date", "날짜"),
    "actor": ("actor", "speaker", "대상인물", "발언자"),
    "organization": ("organization", "position", "기관", "직책"),
    "venue": ("venue", "place", "발언장소", "매체"),
    "quote": ("quote", "content", "summary", "주요발언내용", "발언내용", "요약"),
    "keywords": ("keywords", "핵심키워드", "키워드"),
    "source_title": ("source_title", "title", "주요발언기사출처", "기사출처", "대표출처", "제목"),
    "source_url": ("source_url", "url", "출처URL", "URL", "링크"),
    "source_name": ("source_name", "media", "출처명", "언론사", "플랫폼"),
}
```

다운로드 파일명: `speeches.csv`

다운로드 컬럼:

- 날짜
- 대상인물
- 기관
- 발언장소
- 주요발언내용
- 핵심키워드
- 주요발언기사출처
- 출처URL
- 출처명

### 중대재해사례 CSV 필드 alias

```python
INCIDENT_CSV_MAPPING = {
    "company_name": ("company_name", "company", "회사명", "사업장명"),
    "accident_date": ("accident_date", "date", "사고일", "날짜"),
    "accident_summary": ("accident_summary", "summary", "accident_content", "사고내용", "사고개요", "요약"),
    "external_response": ("external_response", "response", "대외대응", "대응"),
    "implication": ("implication", "insight", "시사점"),
    "apology_text": ("apology_text", "사과문"),
    "source_title": ("source_title", "title", "대표출처", "기사출처", "제목"),
    "source_url": ("source_url", "url", "출처URL", "URL", "링크"),
    "source_name": ("source_name", "media", "출처명", "언론사", "플랫폼"),
}
```

다운로드 파일명: `incidents.csv`

다운로드 컬럼:

- 순번
- 회사명
- 사고일
- 사고내용
- 대외대응
- 시사점
- 사과문
- 대표출처
- 출처URL
- 출처명

업로드 시 기존 데이터와 중복되면 insert 대신 update한다. 결과 메시지는 신규, 갱신, 제외, 빈 행 제외 건수를 표시한다.

---

## 16. 종합분석 생성

종합분석은 `generate_summary_analysis()`에서 생성한다.

입력 context:

- 최근 주요인사발언 최대 80건
- 최근 중대재해사례 최대 80건
- 당사 사고 대응 기록 최대 30건

OpenAI Chat Completions API 사용:

- 모델: `OPENAI_MODEL`, 기본 `gpt-4o-mini`
- temperature: 0.25
- 우선 `response_format={"type": "json_object"}` 사용
- 실패 시 response_format 없이 재시도
- quota 429 오류는 별도 메시지로 처리

출력 JSON:

```json
{
  "key_implications": ["주요 시사점 문장"],
  "posco_response": ["포스코그룹 대응방안 문장"]
}
```

프롬프트 요구사항:

- 한국어 작성
- 사실관계가 불명확하면 단정 금지
- 대통령/노동부장관 발언과 중대재해 흐름을 종합
- 경영층 보고 문장
- 정부 안전/노동 정책 변화
- 타사 중대재해 사례와 정부/노동부/수사기관 대외대응
- 포스코의 AI 안전기술, 협력사/중소규모 사업장 지원, 예방 중심 안전관리, 대외 커뮤니케이션 조합

생성 결과는 `analysis_reports`에 `kind='summary'`로 저장한다.

---

## 17. 데이터검색 기능

데이터검색은 `generate_data_search_answer(query)`에서 수행한다.

검색 대상:

- 주요인사발언
- 중대재해사례
- 당사사고 대응방향
- 수집이력
- 종합분석

`database_search_context()`는 다음 데이터를 읽는다.

- 각 테이블별 count
- 주요인사발언 최대 160건
- 중대재해사례 최대 160건
- 당사 사고 대응 기록 최대 160건
- 수집 이력 최대 160건
- 종합분석 최근 20건

검색 보조:

- 자연어 질의에서 2자 이상 한글/영문/숫자 term 추출
- `YYYY년`, `M월`, `M월 D일` 같은 한국어 날짜 표현을 ISO 날짜 검색어로 변환
- 질문에 `주요인사`, `발언`, `중대재해`, `재해사례`, `당사사고`, `대응방향`, `사과문`, `수집`, `이력`, `종합분석`, `시사점`이 포함되면 테이블 가중치 부여

OpenAI 답변 프롬프트:

- 제공된 SQLite 데이터 안에서만 답변
- 데이터에 없는 사실은 없다고 말하기
- 질문에 특정 탭/테이블이 언급되면 해당 테이블 우선
- JSON 객체만 출력

출력 JSON:

```json
{
  "answer": "질문에 대한 답변",
  "evidence": [
    {
      "table": "근거 테이블",
      "id": "행 ID",
      "date": "날짜",
      "title": "제목",
      "summary": "요약",
      "source_url": "원문 URL"
    }
  ]
}
```

OpenAI 답변 생성이 실패하면 `local_data_search_answer()`로 fallback한다.

local fallback:

- 저장 데이터의 키워드 일치와 테이블 가중치로 관련 행 점수화
- 상위 6개 근거 표시
- AI 검색 실패 안내 notice 표시

---

## 18. 당사사고 대응방향 생성

당사 사고 대응 생성은 `generate_company_accident_response(incident_description)`에서 수행한다.

사용자 입력:

- 재해내용
- 사고 일시, 장소, 피해 현황, 현재 확인된 원인, 즉시 조치사항 등 자유 입력

참고 데이터:

- 누적 주요인사발언
- 누적 중대재해사례
- 기존 당사 사고 대응 기록
- 중대재해사례 테이블에 저장된 타사 사과문 최대 30건

OpenAI 출력 JSON:

```json
{
  "apology_text": "언론 배포용 사과문",
  "response_direction": "회사 대응 방향"
}
```

프롬프트 요구사항:

- 한국 대기업의 중대재해 위기대응, 언론 발표문, 정부 정책 대응 전문가 톤
- 방어적 표현보다 책임, 유가족/피해자, 원인조사 협조, 재발방지, 현장 실행 우선
- `apology_text`: 5~8문장
- `response_direction`: 5~8개 문장 또는 문단
- 최근 정부 안전정책 워딩 자연스럽게 반영

생성 결과는 즉시 저장하지 않는다. `company_draft`로 화면에 표시하고, 담당자가 검토·수정 후 저장 버튼을 누르면 `company_accidents`에 저장한다. 저장 시 생성 당시의 `context_for_ai()` 결과를 `context_snapshot`에 저장한다.

---

## 19. 탭별 상세 UI

### 19-1. 종합분석 탭

상단 버튼:

- 기사 링크 보정
- 종합분석 생성

표시 영역:

- 주요 시사점
- 포스코그룹 대응방안
- 최근 주요인사 발언 5건
- 최근 중대재해 5건
- 최근 수집 이력 6건

각 최근 항목은 원문 URL이 유효하면 링크로 표시하고, URL이 유효하지 않으면 텍스트만 표시한다.

### 19-2. 주요인사발언 탭

기능:

- 시작일/종료일 선택
- OpenAI web_search 데이터 추출
- 추출 미리보기
- 확인 후 저장
- CSV 업로드
- CSV 다운로드
- 행별 수정
- 행별 삭제

테이블 컬럼:

| 날짜 | 대상인물·기관 | 발언장소 | 주요발언내용 | 핵심키워드 | 주요발언기사출처 | 관리 |
|---|---|---|---|---|---|---|

수정은 Bootstrap modal에서 처리한다.

### 19-3. 중대재해사례 탭

기능:

- 시작일/종료일 선택
- OpenAI web_search 데이터 추출
- 추출 미리보기
- 확인 후 저장
- CSV 업로드
- CSV 다운로드
- 행별 수정
- 행별 삭제

테이블 컬럼:

| 회사명 | 사고일 | 사고내용 | 대외대응 | 시사점 | 기사출처 | 사과문 | 관리 |
|---|---|---|---|---|---|---|---|

수정은 Bootstrap modal에서 처리한다.

### 19-4. 데이터검색 탭

기능:

- 저장된 앱 데이터를 자연어로 검색
- OpenAI 답변 생성
- OpenAI 실패 시 로컬 키워드 검색 fallback
- 답변과 근거 데이터 표시

예시 질문:

```text
최근 정부가 강조한 안전정책은?
최근 건설업 중대재해 사례 알려줘
노동부 장관이 AI 안전기술 언급한 사례 찾아줘
5월 중대재해 사례만 정리해줘
당사사고 대응방향 중 사과문이 있는 항목을 보여줘
```

### 19-5. 당사사고 대응방향 탭

기능:

- 재해내용 입력
- 대응방향 버튼으로 사과문과 회사 대응 방향 생성
- 생성 결과 검토/수정
- 저장
- 저장된 기록 목록 표시
- 기록별 수정/삭제

저장 기록 표시:

- 입력 재해내용
- 언론 배포용 사과문
- 회사 대응 방향
- 생성 시각

---

## 20. 라우트

통합 앱에서는 `/proj2` prefix 아래에 등록된다.

```text
GET  /proj2/                              메인 화면
POST /proj2/collect                       주요인사발언+중대재해 통합 추출
POST /proj2/collection/save               통합 추출 결과 저장
POST /proj2/source-links/repair           기사 링크 보정

POST /proj2/speeches/extract              주요인사발언 추출
POST /proj2/speeches/save-extracted       주요인사발언 추출 결과 저장
POST /proj2/speeches/upload-csv           주요인사발언 CSV 업로드
POST /proj2/speeches                      직접 추가 제거 안내
POST /proj2/speeches/<id>/update          주요인사발언 수정
POST /proj2/speeches/<id>/delete          주요인사발언 삭제
GET  /proj2/speeches.csv                  주요인사발언 CSV 다운로드

POST /proj2/incidents/extract             중대재해사례 추출
POST /proj2/incidents/save-extracted      중대재해사례 추출 결과 저장
POST /proj2/incidents/upload-csv          중대재해사례 CSV 업로드
POST /proj2/incidents                     직접 추가 제거 안내
POST /proj2/incidents/<id>/update         중대재해사례 수정
POST /proj2/incidents/<id>/delete         중대재해사례 삭제
GET  /proj2/incidents.csv                 중대재해사례 CSV 다운로드

POST /proj2/data-search                   저장 데이터 자연어 검색
POST /proj2/analysis/generate             종합분석 생성

POST /proj2/company-accidents/generate    당사 사고 대응 초안 생성
POST /proj2/company-accidents             당사 사고 대응 저장
POST /proj2/company-accidents/<id>/update 당사 사고 대응 수정
POST /proj2/company-accidents/<id>/delete 당사 사고 대응 삭제
```

단독 실행 시에는 prefix 없이 같은 라우트를 사용한다.

---

## 21. 프론트엔드 JS

`proj2/static/js/app.js`는 다음을 담당한다.

- `form[data-confirm]` 제출 전 `window.confirm()` 표시
- 주요인사발언 수정 modal에 row data 주입
- 중대재해사례 수정 modal에 row data 주입
- 당사 사고 대응 기록 수정 modal에 row data 주입
- Bootstrap 탭이 전환되면 URL hash 갱신
- 페이지 로드 시 hash에 맞는 탭 활성화

모달 수정 form action은 JS에서 행 ID를 기준으로 설정한다.

---

## 22. 스타일 요구사항

`proj2/static/css/app.css`는 다음 UI 톤을 구현한다.

- 기본 Bootstrap 위에 운영형 대시보드 스타일 적용
- 상단 header와 탭 기반 레이아웃
- 좌우 여백은 `container-fluid px-3 px-lg-4`
- 탭은 모바일에서 가로 스크롤
- 카드/테이블 패널은 8px radius
- 테이블은 넓은 데이터를 위해 최소 너비와 가로 스크롤 지원
- 데이터 테이블의 긴 텍스트는 `white-space: pre-line`, `overflow-wrap: anywhere`
- 액션 버튼은 nowrap 처리
- 당사 사고 대응 기록은 3컬럼 레이아웃, 모바일에서는 1컬럼
- 기본 톤은 어두운 배경의 모듈형 대시보드 스타일
- `theme-toggle.css`, `theme-toggle.js`와 연동해 다크/화이트 테마를 지원

---

## 23. 예외 처리

필수 예외 처리:

- 날짜 형식 오류
- 시작일이 종료일보다 늦은 경우
- OpenAI API 키 없음
- OpenAI quota 429 오류
- OpenAI JSON 파싱 실패
- CSV 파일 없음
- CSV 파일 비어 있음
- CSV 인코딩 오류
- source URL 유효성 실패
- YouTube 재생 불가 URL 제외
- 데이터검색 OpenAI 실패 시 로컬 fallback
- 수집 실패 시 `collection_runs`에 failed 상태 저장

오류/성공 메시지는 Flask `flash()`로 사용자에게 표시한다.

---

## 24. 실행 방법

### 의존성 설치

루트 통합 실행 기준:

```bash
python3 -m pip install -r requirements.txt
```

`proj2`만 별도 의존성을 설치할 경우:

```bash
python3 -m pip install -r proj2/requirements.txt
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

로그인 후 `/proj2`로 이동한다.

### proj2 단독 실행

```bash
cd /path/to/pr/proj2
python3 app.py
```

임시 포트 지정:

```bash
PORT=5002 python3 app.py
```

단독 실행 시에는 통합 앱의 로그인 보호 없이 `proj2` 화면이 열린다.

---

## 25. 핵심 개발 조건

- `proj2/app.py`의 단일 파일 구조를 유지한다.
- 통합 앱의 Blueprint로 등록 가능해야 한다.
- 단독 실행도 가능해야 한다.
- 루트 `.env`를 사용한다.
- DB는 `proj2/instance/safety_labor.db`에 생성한다.
- OpenAI Responses API `web_search`로 수집한다.
- OpenAI Chat Completions API로 종합분석, 데이터검색 답변, 당사 사고 대응을 생성한다.
- Gemini API 또는 Google Search Grounding은 사용하지 않는다.
- 데이터 추출 결과는 즉시 저장하지 않고 미리보기 후 저장한다.
- 주요인사발언과 중대재해사례를 분리 추출할 수 있어야 한다.
- CSV 업로드/다운로드를 지원한다.
- 저장 데이터 수정/삭제를 지원한다.
- 기사 원문 URL은 유효성 검증 후 표시한다.
- legacy grounding redirect URL은 보정한다.
- 데이터검색은 OpenAI 실패 시 로컬 키워드 fallback을 제공한다.
- 당사 사고 대응 생성 결과는 담당자 검토 후 저장한다.
- 관리자 권한과 일반 로그인 권한을 구분한다.
- Bootstrap 기반 반응형 UI와 테마 토글을 지원한다.

---

## 26. 최종 요청

위 요구사항에 따라 현재 `proj2` 모듈과 동일한 수준의 Flask 웹 애플리케이션 코드를 작성해줘.

다음 조건을 반드시 만족해줘.

- 루트 통합 앱과 `proj2` 단독 실행을 모두 고려
- `proj2/app.py`에 DB 스키마, 수집, 분석, CSV, 라우팅 구현
- `proj2/templates/proj2/index.html` 포함
- `proj2/static/css/app.css`, `proj2/static/js/app.js` 포함
- `proj2/requirements.txt` 포함
- 루트 `.env` 사용
- SQLite 누적 저장
- OpenAI web_search 기반 데이터 추출
- 주요인사발언/중대재해사례 분리 추출과 저장 미리보기
- CSV 업로드/다운로드
- 저장 데이터 수정/삭제
- 기사 링크 검증과 보정
- 종합분석 생성 및 저장
- 저장 데이터 자연어 검색
- 당사 사고 사과문 및 대응방향 생성
- 관리자 권한 보호
- Bootstrap 기반 반응형 탭 UI
- 다크/화이트 테마 토글
- 오류 처리와 flash 메시지
- 실행 방법과 설치 명령 포함
- 코드 전체를 바로 실행 가능한 수준으로 작성
