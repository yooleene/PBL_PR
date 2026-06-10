# 포스코 이슈 분석 AI 웹앱 개발 프롬프트

## 1. 개발 목표

포스코 홍보·대외협력 담당자가 특정 **사업회사**와 **이슈 키워드**를 입력하면, 네이버 뉴스 기사 원문, 회사 내부 자료(RAG), 네이버 데이터랩 검색 트렌드를 종합하여 **경영진용 이슈 분석 리포트**를 자동 생성하는 Flask 웹 애플리케이션을 개발한다.

단순 뉴스 요약이 아니라, 입력한 사업회사 관점에서 다음 질문에 답하는 것을 목표로 한다.

- 지금 이 이슈가 해당 사업회사에 왜 중요한가
- 기사에서 확인되는 직접·간접 관련도는 어느 정도인가
- 사업, 운영, 재무, 평판, 규제 측면의 리스크는 무엇인가
- 지금 홍보·대외협력 조직이 어떤 메시지와 액션을 준비해야 하는가

---

## 2. 서비스 컨셉

앱 이름은 **이슈 분석 AI | Module 3**으로 한다.

사용자는 메인 화면에서 다음 2개 항목을 입력한다.

- 사업회사 선택
- 분석 키워드 입력

분석 조건은 항상 다음 형식으로 구성한다.

```text
{사업회사명} AND {키워드}
```

예시는 다음과 같다.

```text
포스코홀딩스 AND 노란봉투법
포스코퓨처엠 AND 리튬 공급망
포스코이앤씨 AND 건설 안전
포스코인터내셔널 AND 미얀마 가스전
```

입력 후 백그라운드 작업으로 기사 수집, 내부 자료 검색, 데이터랩 조회, AI 분석을 수행하고, 사용자는 진행 화면과 결과 화면에서 상태를 확인한다.

---

## 3. 기술 스택

- 백엔드: Python 3 + Flask
- 웹 서버: Flask 개발 서버, 운영 배포 시 Gunicorn
- 뉴스 수집: Naver Search News API + requests + BeautifulSoup4
- 트렌드 데이터: Naver DataLab Search API
- AI 리포트 생성: OpenAI Chat Completions API
- AI 모델 fallback 순서:
  - `gpt-5.4`
  - `gpt-5.4-mini`
  - `gpt-5.4-nano`
- 임베딩/RAG: Google Gemini Embedding API `text-embedding-004`
- 벡터DB: ChromaDB PersistentClient
- 작업 상태 저장: SQLite
- 문서 파싱:
  - TXT / MD: UTF-8 텍스트
  - PDF: PyMuPDF
  - DOCX: python-docx
- 프론트엔드:
  - Jinja2 템플릿
  - 자체 CSS 기반 다크 대시보드
  - Chart.js
  - Lucide Icons
  - Google Fonts `Noto Sans KR`, `JetBrains Mono`
- 실행 포트: `5001`
- 반응형: PC + 모바일 지원

---

## 4. `.env` 설정

프로젝트 루트 또는 상위 폴더의 `.env` 파일을 로드한다.

필수 또는 선택 환경변수는 다음과 같다.

```env
# Flask
APP_HOST=127.0.0.1
APP_PORT=5001
APP_DEBUG=false
FLASK_SECRET_KEY=change-this-secret

# Data paths
APP_DATA_DIR=./data
APP_UPLOAD_DIR=./data/uploads
APP_CHROMA_DIR=./data/chroma_db
APP_TASK_DB=./data/tasks.sqlite3

# AI
OPENAI_API_KEY=<OpenAI API 키>
GEMINI_API_KEY=<Google Gemini API 키>
GOOGLE_API_KEY=<GEMINI_API_KEY 대체 가능>

# Naver News Search API
NAVER_CLIENT_ID=<네이버 검색 API Client ID>
NAVER_CLIENT_SECRET=<네이버 검색 API Client Secret>

# Naver DataLab API
NAVER_DATALAB_CLIENT_ID=<네이버 데이터랩 Client ID>
NAVER_DATALAB_CLIENT_SECRET=<네이버 데이터랩 Client Secret>

# Optional
APP_USER_AGENT=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
```

`config.py`는 다음 순서로 `.env`를 로드한다.

1. 현재 프로젝트의 상위 폴더 `.env`
2. 현재 프로젝트 폴더 `.env`

상위 폴더 값을 먼저 읽고, 현재 폴더 값은 기본적으로 기존 값을 덮어쓰지 않도록 한다.

---

## 5. 프로젝트 구조

다음 구조로 전체 코드를 작성한다.

```text
proj3/
├── __init__.py
├── app.py
├── config.py
├── requirements.txt
├── README.md
├── wsgi.py
├── data/
│   ├── chroma_db/
│   └── tasks.sqlite3
├── services/
│   ├── __init__.py
│   ├── gemini_ai.py
│   ├── naver_api.py
│   ├── naver_datalab.py
│   ├── rag.py
│   └── task_store.py
└── templates/
    └── proj3/
        ├── index.html
        ├── progress.html
        ├── result.html
        └── documents.html
```

---

## 6. 필수 패키지

`requirements.txt`에는 다음 패키지를 포함한다.

```text
Flask==3.1.3
python-dotenv==1.2.2
requests==2.33.1
beautifulsoup4==4.14.3
Markdown==3.10.2
chromadb==1.5.7
openai==2.32.0
google-genai==1.71.0
PyMuPDF
python-docx
gunicorn>=23.0.0
```

---

## 7. 사업회사 선택

메인 화면에서는 다음 4개 사업회사를 선택할 수 있어야 한다.

| 회사 | 역할 | 주요 이슈 맥락 |
|---|---|---|
| 포스코홀딩스 | 그룹 지주회사 | ESG, 지배구조, 탄소중립, HyREX, 그룹 전략 |
| 포스코이앤씨 | 건설·엔지니어링 | 건설안전, 더샵, 중대재해처벌법, PF 리스크 |
| 포스코인터내셔널 | 트레이딩·자원개발 | LNG, 곡물, 미얀마, 공급망, 통상 |
| 포스코퓨처엠 | 2차전지 소재 | 양극재, 음극재, 리튬, IRA, 배터리 공급망 |

회사별 설명 박스를 입력 화면에 표시한다.

사업회사 선택 값은 분석 프롬프트와 RAG 검색 필터에 반드시 반영한다.

---

## 8. Flask 라우트

필수 라우트는 다음과 같다.

```text
GET  /                         메인 분석 화면
POST /analyze                  분석 작업 생성 및 진행 화면 렌더링
GET  /status/<task_id>         작업 진행 상태 JSON API
GET  /result/<task_id>         분석 결과 화면
GET  /api/report/<task_id>     AI 리포트 준비 상태 및 결과 JSON API

GET  /documents                RAG 문서 관리 화면
POST /upload                   문서 업로드 및 벡터DB 저장
POST /delete_doc               업로드 문서 삭제
```

Blueprint 이름은 `proj3`로 지정한다.

```python
bp = Blueprint("proj3", __name__, template_folder="templates")
```

`create_app()` 팩토리를 구현하고, `app.py` 직접 실행과 `wsgi.py` Gunicorn 실행을 모두 지원한다.

---

## 9. 분석 작업 흐름

`POST /analyze` 요청 시 다음을 수행한다.

1. `keyword`를 form에서 읽고 앞뒤 공백 제거
2. `company_name`을 form에서 읽고 기본값은 `포스코홀딩스`
3. 키워드가 비어 있으면 메인 화면으로 redirect
4. `uuid.uuid4()` 기반 8자리 `task_id` 생성
5. SQLite에 작업 row 생성
6. 백그라운드 `threading.Thread`로 `_run_analysis()` 실행
7. `progress.html` 렌더링

분석 함수 `_run_analysis(task_id, keyword, company_name)`는 다음 순서로 동작한다.

```text
1단계: 네이버 뉴스에서 기사 원문 수집
2단계: 기사 수, 날짜별 건수, 매체별 건수 추출
3단계: RAG 내부 자료 검색 + 네이버 데이터랩 조회
4단계: AI 리포트 생성
5단계: Markdown 리포트를 HTML로 변환
6단계: 경영진 3줄 요약 생성
7단계: 완료 상태 저장
```

각 단계마다 `set_status(task_id, step, msg)`로 진행 상태를 저장한다.

오류 발생 시:

- `status_step = -1`
- 오류 메시지를 status에 저장
- 가능한 경우 결과 화면에 오류 HTML 저장
- 전체 서버가 죽지 않도록 예외 처리

---

## 10. 작업 상태 저장 방식

분석 진행 상태와 결과는 인메모리가 아니라 SQLite에 저장한다.

파일 기본 경로:

```text
data/tasks.sqlite3
```

SQLite 테이블은 다음 구조로 생성한다.

```sql
CREATE TABLE IF NOT EXISTS analysis_tasks (
    task_id TEXT PRIMARY KEY,
    status_step INTEGER NOT NULL DEFAULT 0,
    status_msg TEXT NOT NULL DEFAULT '대기 중...',
    result_json TEXT,
    ready INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
```

필수 구현 함수:

```python
create_task(task_id, keyword, company_name)
set_status(task_id, step, msg)
get_status(task_id)
set_result(task_id, result)
update_result(task_id, updates)
get_result(task_id)
```

동시 접근 안정성을 위해 다음을 적용한다.

- `threading.Lock` 기반 초기화 보호
- `sqlite3.Row` row factory
- `PRAGMA busy_timeout=30000`
- `PRAGMA journal_mode=WAL`
- JSON 저장 시 `ensure_ascii=False`

---

## 11. 네이버 뉴스 수집 로직

`services/naver_api.py`에 `get_naver_inlink_articles(keyword, display=100, max_articles=100)`를 구현한다.

### 11.1 Naver Search News API 호출

요청 URL:

```text
https://openapi.naver.com/v1/search/news.json?query={encoded_keyword}&display={display}&sort=sim
```

헤더:

```python
{
    "X-Naver-Client-Id": NAVER_CLIENT_ID,
    "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
}
```

응답에서 `items`를 읽는다.

API 호출 실패 시:

- 콘솔에 오류 출력
- 빈 문자열 반환

### 11.2 네이버 인링크 기사 필터

네이버 뉴스 원문 크롤링이 가능한 기사만 분석 대상으로 삼는다.

조건:

```python
"n.news.naver.com" in item["link"]
```

필터링 후 `max_articles`개만 크롤링한다.

### 11.3 기사 본문 크롤링

기사별로 다음 값을 추출한다.

- 제목
- 매체명
- 일시
- 링크
- 본문

제목은 `<b>` 태그 제거 후 HTML entity를 unescape한다.

본문 선택자:

```text
#dic_area
```

매체명 선택자:

```text
.media_end_head_top_logo img
```

매체명은 `title` 속성을 우선 사용하고, 없으면 `alt` 속성을 사용한다.

본문 수집 성공 시 다음 형식으로 반환한다.

```text
[기사 1]
- 제목: ...
- 매체: ...
- 일시: ...
- 링크: ...
- 본문: ...
```

기사 간 구분자는 다음을 사용한다.

```text

---

```

크롤링은 `ThreadPoolExecutor(max_workers=10)`로 병렬 처리하고, 결과는 원래 검색 순서대로 정렬한다.

개별 기사 크롤링 실패 시 전체 작업을 중단하지 않고 해당 기사는 제외한다.

전체 수집 결과가 비어 있으면 분석 실패로 처리한다.

---

## 12. 기사 통계 추출

수집된 기사 텍스트에서 다음 통계를 추출한다.

- 날짜별 보도 건수
- 매체별 보도 건수

`parsed_articles` 문자열을 줄 단위로 읽고 다음 prefix를 찾는다.

```text
- 매체:
- 일시:
```

매체명이 `알 수 없음`이 아니면 카운트한다.

일시는 `email.utils.parsedate_to_datetime()`으로 파싱한 뒤 다음 형식으로 변환한다.

```text
MM.DD
```

예:

```text
Wed, 16 Apr 2026 09:00:00 +0900 → 04.16
```

결과는 JSON 문자열로 저장해 결과 화면 Chart.js 데이터로 사용한다.

---

## 13. 네이버 데이터랩 연동

`services/naver_datalab.py`에 다음 함수를 구현한다.

```python
get_search_trend(keyword, days=90)
get_age_trend(keyword, days=30)
get_keyword_comparison(keywords, days=30)
```

데이터랩 키가 없으면 오류를 내지 말고 `None`을 반환한다.

### 13.1 일별 검색 트렌드

최근 90일 기준으로 일별 검색량 상대 지수를 조회한다.

요청 API:

```text
POST https://openapi.naver.com/v1/datalab/search
```

요청 body:

```json
{
  "startDate": "YYYY-MM-DD",
  "endDate": "YYYY-MM-DD",
  "timeUnit": "date",
  "keywordGroups": [
    {
      "groupName": "키워드",
      "keywords": ["키워드"]
    }
  ]
}
```

반환 형식:

```python
{
    "dates": ["YYYY-MM-DD", ...],
    "values": [12.3, 45.6, ...],
    "keyword": keyword
}
```

### 13.2 연령대별 검색 트렌드

최근 30일 기준으로 다음 연령대별 상대 검색량 평균을 구한다.

| 표시명 | Naver age code |
|---|---|
| 20대 | 3 |
| 30대 | 4 |
| 40대 | 5 |
| 50대 | 6 |
| 60대+ | 7 |

반환 예:

```python
{
    "20대": 18.2,
    "30대": 44.1,
    "40대": 72.5,
    "50대": 63.0,
    "60대+": 39.4
}
```

### 13.3 키워드 비교

사용자가 입력한 키워드가 여러 단어로 구성되어 있으면 공백 기준으로 최대 5개까지 분리하여 비교한다.

예:

```text
리튬 공급망 규제 → ["리튬", "공급망", "규제"]
```

각 키워드의 최근 30일 평균 검색량 상대 지수를 반환한다.

---

## 14. RAG 문서 관리

`services/rag.py`에 ChromaDB 기반 RAG 시스템을 구현한다.

### 14.1 저장소

기본 ChromaDB 저장 경로:

```text
data/chroma_db
```

컬렉션명:

```text
company_docs
```

거리 기준:

```python
metadata={"hnsw:space": "cosine"}
```

### 14.2 임베딩

Google Gemini Embedding API를 사용한다.

```python
client = genai.Client(api_key=GEMINI_API_KEY or GOOGLE_API_KEY)
client.models.embed_content(
    model="text-embedding-004",
    contents=text
)
```

### 14.3 문서 청킹

문서는 다음 기준으로 분할한다.

```python
chunk_size = 500
overlap = 50
```

각 청크의 metadata:

```python
{
    "doc_id": doc_id,
    "filename": filename,
    "category": category,
    "company": company,
    "chunk_index": i
}
```

`doc_id`는 다음 형식으로 만든다.

```text
{uuid8}_{filename}
```

### 14.4 필수 함수

다음 함수를 구현한다.

```python
add_document(text, filename, category="기타", company="포스코홀딩스")
search_documents(query, company=None, n_results=5)
search_and_format_for_prompt(query, company=None, n_results=5)
get_all_documents()
delete_document(doc_id)
get_doc_count()
```

### 14.5 분석 시 RAG 검색 방식

분석 쿼리:

```text
{company_name} {keyword}
```

검색은 2회 수행한다.

1. 선택한 사업회사 자료에서 상위 5개 청크 검색
2. `포스코그룹 공통` 자료에서 상위 3개 청크 검색

검색 결과가 있으면 AI 프롬프트에 다음 형식으로 넣는다.

```text
[내부자료 1] (유사도: 0.812)
- 파일: ...
- 분류: ...
- 관련회사: ...
- 내용: ...
```

자료가 없으면 다음 문자열을 넣는다.

```text
(관련 내부 자료 없음)
```

---

## 15. 문서 업로드 기능

`/documents` 화면에서 회사 내부 자료를 업로드하고 관리할 수 있게 한다.

지원 확장자:

```text
txt, pdf, docx, md
```

허용하지 않는 확장자 업로드 시:

- 저장하지 않음
- 문서 관리 화면으로 redirect
- 오류 메시지 표시

문서 업로드 form 필드:

| 필드 | 설명 |
|---|---|
| file | 업로드 파일 |
| company | 관련 사업회사 |
| category | 자료 분류 |

회사 선택 옵션:

```text
포스코홀딩스
포스코이앤씨
포스코인터내셔널
포스코퓨처엠
포스코그룹 공통
```

자료 분류 옵션:

```text
입장문
보도자료
내부자료
사과문
기타
```

업로드 후:

1. 파일명을 `secure_filename()`으로 정리
2. `APP_UPLOAD_DIR`에 저장
3. 파일 텍스트 추출
4. ChromaDB에 청크 단위 저장
5. 저장된 청크 수를 flash 메시지로 표시

문서 목록에서는 다음 정보를 표시한다.

- 파일명
- 관련 사업회사
- 자료 분류
- 청크 수
- 삭제 버튼

삭제 시 `doc_id`에 해당하는 모든 청크를 삭제한다.

---

## 16. AI 분석 모듈

`services/gemini_ai.py` 파일에 AI 호출 및 프롬프트 구성을 구현한다.

파일명은 `gemini_ai.py`로 유지하되, 리포트 생성은 OpenAI Chat Completions API를 사용한다.

### 16.1 OpenAI 호출 함수

`_call_gpt(prompt, temperature=0.2, max_retries=2)`를 구현한다.

모델 fallback 순서:

```python
models = ["gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano"]
```

에러 처리:

- 429 또는 rate limit: 다음 모델로 이동
- 404 또는 not found: 다음 모델로 이동
- 500 또는 503: 10초 대기 후 재시도
- 기타 오류: 오류 문자열 반환
- 모든 모델 실패: `"❌ API 호출 실패."` 반환

### 16.2 회사 컨텍스트

AI 프롬프트에 사용할 회사별 컨텍스트를 딕셔너리로 둔다.

```python
COMPANY_CONTEXT = {
    "포스코홀딩스": {
        "role": "그룹 지주회사",
        "business": "철강, 2차전지소재, 에너지, 인프라 총괄",
        "keywords": "ESG, 지배구조, 탄소중립, HyREX",
        "competitors": "현대제철, 일본제철, 바오우강철, ArcelorMittal",
        "policy_focus": "CBAM, 산업안전보건법, 노동법, ESG 공시",
        "tone": "격조 있는 톤",
        "is_holdings": True
    },
    "포스코이앤씨": {
        "role": "건설·엔지니어링",
        "business": "건축(더샵), 토목, 플랜트, 해외인프라",
        "keywords": "건설안전, 더샵, 중대재해법",
        "competitors": "현대건설, 삼성물산, GS건설, DL이앤씨",
        "policy_focus": "중대재해처벌법, PF리스크, 분양가상한제",
        "tone": "안전 최우선, 기술력 강조",
        "is_holdings": False
    },
    "포스코인터내셔널": {
        "role": "트레이딩·자원개발",
        "business": "철강트레이딩, 곡물, LNG, 미얀마가스전",
        "keywords": "미얀마, LNG, 곡물, 공급망",
        "competitors": "삼성물산 상사, LX인터, 미쓰비시",
        "policy_focus": "통상정책, 미얀마제재, 공급망실사법",
        "tone": "글로벌 실리, 지정학 신중",
        "is_holdings": False
    },
    "포스코퓨처엠": {
        "role": "2차전지 소재",
        "business": "양극재(NCM·LFP), 음극재, 리튬·니켈",
        "keywords": "양극재, 리튬, IRA, 배터리",
        "competitors": "에코프로비엠, 엘앤에프, CATL, BASF",
        "policy_focus": "IRA, EU CRMA, 배터리여권",
        "tone": "기술혁신, 공급망 확보 부각",
        "is_holdings": False
    }
}
```

### 16.3 리포트 생성 함수

함수명:

```python
analyze_issue_with_gemini(keyword, parsed_articles, rag_data, company_name="포스코홀딩스", issue_query=None)
```

AI에게 부여할 역할:

```text
너는 글로벌 전략컨설팅펌의 시니어 이슈·리스크 파트너이자 {company_name} 홍보/대외협력 자문역이다.
```

분석 목표:

```text
단순 뉴스 요약이 아니라 "{company_name} AND {keyword}" 조건에서 확인된 기사만 근거로,
{company_name}의 의사결정에 필요한 So what / Now what을 도출한다.
```

---

## 17. AI 분석 조건

AI 프롬프트에는 다음 조건을 반드시 포함한다.

1. 검색 의도는 반드시 `{company_name} AND {keyword}`이다.
2. 기사에 `{company_name}`과 `{keyword}`가 모두 명시되거나 직접 연결되는 경우만 직접 관련으로 본다.
3. 회사 언급이 없고 업계 일반론만 있는 기사는 배경으로만 사용한다.
4. 다른 계열사, 경쟁사, 일반 산업 뉴스는 해당 회사에 미치는 연결 경로가 입증될 때만 반영한다.
5. 포스코홀딩스가 아닌 사업회사 선택 시 그룹 전체 관점으로 확장하지 않는다.
6. 포스코홀딩스 선택 시에만 그룹 계열사 파급을 별도 분석한다.
7. 본문에서 `[기사N]` 표기는 금지한다.
8. 출처는 참고기사 테이블에만 둔다.
9. 숫자, 날짜, 이해관계자, 인과관계가 없는 추정은 `⚠️AI추론:` 접두어를 붙인다.
10. 개조식으로 작성한다.
11. 각 항목은 1~2줄 중심으로 작성한다.
12. 표는 우선순위, 온도, 확률 내림차순으로 작성한다.
13. 모든 섹션에서 `{company_name}에 그래서 무엇이 문제인가`와 `지금 무엇을 해야 하는가`가 드러나야 한다.

---

## 18. AI 분석 프레임

AI 프롬프트에 다음 분석 프레임을 포함한다.

- 관련도 필터:
  - 직접 관련
  - 간접 관련
  - 배경
  - 제외
- 영향 경로:
  - 이슈
  - 이해관계자 반응
  - 사업/운영/재무/평판 영향
  - 커뮤니케이션 액션
- 인사이트 깊이:
  - 표면 이슈 설명보다 트리거, 2차 파급, 의사결정 옵션, 선제 메시지 우선
- 근거 부족 시:
  - 과장하지 말고 `확인 필요` 또는 `근거 부족` 명시
- RAG 자료:
  - 내부 원보이스
  - 금지 표현
  - 기존 입장과 상충 여부 점검

---

## 19. AI 리포트 출력 구조

AI는 Markdown 형식으로 다음 12개 섹션을 출력한다.

리포트 제목:

```markdown
## 🔍 '{keyword}' 이슈 대시보드 — {company_name}
```

### 19.1 핵심 브리핑

다음 관련도 판정 표를 포함한다.

| 구분 | 건수 | 판단 기준 | 분석 반영 |
|---|---:|---|---|
| 직접 관련 | N건 | 회사+키워드가 같은 맥락에서 확인 | 핵심 근거 |
| 간접 관련 | N건 | 사업/공급망/규제 연결 경로 확인 | 보조 근거 |
| 배경 | N건 | 업계 일반론, 회사 직접 연결 약함 | 맥락만 반영 |
| 제외 | N건 | 무관·중복·낮은 신뢰 | 반영 제외 |

포함 항목:

- 핵심 팩트 2~3개
- 회사 영향
- 경영진 판단
- 보도 추이
- 즉시 판단

### 19.2 키워드 스니펫

| 항목 | 내용 |
|---|---|
| 정의 | 키워드 의미 |
| 배경 | 사건·제도·시장 배경 |
| 회사 직접 연관성 | 사업, 공급망, 고객, 현장, 정책 노출 중 연결점 |
| 회사 관점의 쟁점 | 관리해야 할 쟁점 |
| 현재 단계 | 발생기/확산기/절정기/수습기 |
| 근거 공백 | 추가 확인 필요사항 |

### 19.3 보도 확산 경로

기사 일시 기준 시간순으로 최소 5개 이벤트를 정리한다.

| 시점 | 매체 | 보도 내용 | 회사 관련도 | 확산 단계 |
|---|---|---|---|---|
| 일시 | 매체명 | 최초 공개 팩트 | 직접/간접/배경 | 발화/확산/증폭 |

추가 분석:

- 어떤 매체/프레임이 이슈를 키웠는지
- 회사가 주체, 대상, 비교, 배경 중 어떤 방식으로 언급되는지
- 다음 확산 트리거

### 19.4 쟁점 클러스터

| 우선순위 | 쟁점 | 왜 중요한가 | 회사 영향 경로 | 대응 방향 |
|---|---|---|---|---|
| A | 쟁점명 | 수치·팩트 | 이슈→이해관계자→사업/평판 영향 | 즉시 액션 |

추가 인사이트:

- 회사 의사결정 변수 2~3개
- 잘못 대응할 경우의 2차 리스크

### 19.5 매체별 논조

| 매체 | 보도 프레임 | 논조 | 온도(1~5) | 회사 노출 | 우선순위 | 대응 힌트 |
|---|---|---|---:|---|---|---|
| 매체명 | 규제/안전/실적/노동/공급망 | 긍정/중립/경계/부정 | N | 직접/간접/없음 | A/B/C | 한줄 |

논조 종합 표:

| 구분 | 건수 | 비율 | 회사 관점 해석 |
|---|---:|---:|---|
| 🟢긍정 | N건 | N% | |
| 🟡중립 | N건 | N% | |
| 🟠경계 | N건 | N% | |
| 🔴부정 | N건 | N% | |

리스크 키워드 네트워크:

| 키워드 | 연결 키워드 | 강도 | 빈도 | 회사 리스크 의미 |
|---|---|---|---:|---|

### 19.6 이해관계자 동향

| 이해관계자 | 동향 | 회사에 미치는 압력 | 관찰 포인트 |
|---|---|---|---|
| 정부·관계부처 | 법안, 시행일, 예산, 발언 | 높음/중간/낮음 | |
| 경쟁사·업계 | 기업명, 대응, 수치 | | |
| 노동계·시민사회 | 요구, 규모 | | |
| 투자자·고객 | 실적, 계약, 신뢰 영향 | | |
| 해외·글로벌 | 국가, 기업, 사례 | | |

### 19.7 리스크 매트릭스

| 등급 | 리스크 | 확률 | 재무영향 | 평판영향 | 회사 영향 경로 | 조기경보 지표 |
|---|---|---:|---|---|---|---|
| 🔴 | 명칭 | N% | N억원/확인필요 | 높음/중간/낮음 | 구체적 | 지표 |

히든 리스크는 `⚠️AI추론:` 표시와 함께 별도 표로 정리한다.

| 시나리오 | 트리거 | 영향 | 대비 |
|---|---|---|---|

포스코홀딩스 선택 시에만 다음 표를 추가한다.

| 계열사 | 영향도 | 파급 경로 | 리스크/기회 |
|---|---|---|---|
| 포스코이앤씨 | 🔴/🟡/🟢 | 경로 | 한줄 |
| 포스코인터내셔널 | 🔴/🟡/🟢 | 경로 | 한줄 |
| 포스코퓨처엠 | 🔴/🟡/🟢 | 경로 | 한줄 |

### 19.8 타임라인

| 시기 | 예상 이벤트 | 관찰 신호 | 영향 | 대응 |
|---|---|---|---|---|
| ~1주 | 이벤트 | 뉴스/정부/노조/시장 신호 | 🔴/🟡/🟢 | 방안 |
| ~2주 | | | | |
| ~1개월 | | | | |
| ~3개월 | | | | |

### 19.9 회사 시사점

포함 항목:

- 사업/운영 관점 파급도
- 재무/투자자 관점 파급도
- 평판/대외협력 관점 파급도
- 기회요인
- 의사결정 옵션

의사결정 옵션 표:

| 옵션 | 장점 | 리스크 | 추천도 |
|---|---|---|---|
| 관망 | | | 낮음/중간/높음 |
| 선제 설명 | | | |
| 적극 대응 | | | |

### 19.10 원보이스

다음 4개 메시지를 생성한다.

```markdown
**🛡️방어적**: "200자 이상, 확인된 팩트 중심"
**✊적극적**: "200자 이상, 회사의 역할·개선·책임 강조"
**🚨위기대응**: "200자 이상, 책임 회피 없이 조치 중심"
**📢내부커뮤니케이션(직원)**: "150자 이상, 임직원 혼선 방지"
```

마지막에 다음 문구를 포함한다.

```text
※AI생성초안. 법무팀검토후사용.
```

### 19.11 예상 Q&A

기자, 투자자, 임직원, 정부, 시민사회가 물을 수 있는 질문을 예상한다.

| No. | 예상질문 | 질문 의도 | 권장답변 |
|---:|---|---|---|
| 1 | 가능성 높은 질문 | 사실확인/책임/대책/일정 | 답변 |
| 2 | 질문 | | |
| 3 | 질문 | | |
| 4 | 질문 | | |
| 5 | 공격적 질문 | | |

마지막에 다음 문구를 포함한다.

```text
※AI생성초안. 법무팀검토후사용.
```

### 19.12 참고기사

전체 기사 목록을 최신순으로 정리한다.

| No. | 관련도 | 매체 | 기사제목 | 일시 | 링크 |
|---:|---|---|---|---|---|
| 1 | 직접/간접/배경 | 매체명 | 제목 | YYYY.MM.DD HH:MM | URL |

분석에서 제외한 기사는 관련도에 `제외`로 표시하거나 생략한다.

---

## 20. 경영진 3줄 요약 생성

AI 리포트 생성 후 별도 함수로 경영진 브리핑 카드용 3줄 요약을 만든다.

함수명:

```python
generate_summary_card(report_text, keyword, company_name="포스코홀딩스")
```

입력:

- 전체 리포트 Markdown
- 키워드
- 사업회사명

요구사항:

- 각 줄은 45~75자 수준으로 구체적으로 작성
- 단순 요약이 아니라 상황 판단, 핵심 리스크, 즉시 권고가 드러나야 함
- 회사 관점의 직접 영향과 행동 포함
- 수치가 있으면 반드시 포함
- 수치가 없으면 `확인 필요` 명시
- 형식 외 문장 출력 금지

출력 형식:

```text
📌[{keyword}]: (상황 판단+왜 지금 중요한지+수치)
⚠️리스크: (회사 직접 리스크+트리거+수치/확인필요)
✅권고: (오늘 착수할 조치+담당 기능+메시지 방향)
```

---

## 21. Markdown 변환

AI가 생성한 Markdown 리포트는 서버에서 HTML로 변환한다.

사용 라이브러리:

```python
markdown.markdown(
    report_md,
    extensions=["tables", "fenced_code", "nl2br"]
)
```

변환 결과:

- `report_md`: 복사용 원본 Markdown
- `report_html`: 화면 표시용 HTML

두 값을 모두 SQLite 결과 JSON에 저장한다.

---

## 22. 메인 화면 UI

`templates/proj3/index.html`을 구현한다.

화면 구성:

- 상단 nav
  - 로고: `이슈분석 AI Module 3`
  - 자료관리 링크
- 중앙 hero
  - eyebrow: `PR Issue Intelligence`
  - 제목: `이슈 분석 AI`
  - 설명: 최신 뉴스와 내부 자료 기반 리포트 생성
- 분석 설정 카드
  - 사업회사 select
  - 회사별 설명 박스
  - 키워드 input
  - 추천 키워드 quick chip
- 제출 버튼
  - 텍스트: `이슈 분석 시작`
  - 아이콘: search
- 분석 프로세스 안내 박스
- 제출 후 loading overlay

추천 키워드 chip:

```text
노란봉투법
리튬 공급망
건설 안전
탄소중립 규제
```

스타일:

- 다크 배경
- 8px 이하 border-radius
- 포스코 업무용 대시보드 느낌
- 과도한 마케팅형 히어로 금지
- 모바일에서는 카드 패딩과 헤더 크기를 줄임

---

## 23. 진행 화면 UI

`templates/proj3/progress.html`을 구현한다.

분석 시작 직후 사용자가 보는 화면이다.

표시 요소:

- 회사명 badge
- `'{keyword}' 분석 중` 제목
- 진행 bar
- 3단계 step panel
  - 뉴스 기사 수집
  - 기사 원문 파싱
  - 내부 자료 + 트렌드 검색
- 현재 상태 메시지

프론트엔드 동작:

- `GET /status/<task_id>`를 1초 간격으로 polling
- `step = -1`이면 오류 메시지를 빨간색으로 표시하고 polling 중단
- `step >= 4`이면 모든 단계를 완료 표시하고 0.6초 후 결과 화면으로 이동

결과 화면 URL:

```text
/result/<task_id>
```

---

## 24. 결과 화면 UI

`templates/proj3/result.html`을 구현한다.

결과 화면은 단순 문서 뷰어가 아니라 경영진용 대시보드로 구성한다.

### 24.1 상단 nav

표시 항목:

- 로고: `이슈분석 AI Module 3`
- 분석 조건 pill: `{company_name} AND {keyword}`
- 사업회사
- 기사 수
- RAG 검색 결과 수
- 분석 시점

버튼:

- 새 검색
- 자료관리
- 경영진 브리프
- 복사
- 인쇄

### 24.2 좌측 목차 rail

데스크톱에서는 좌측 sticky rail을 둔다.

구성:

- `Report Contents` 제목
- 읽기 진행률 bar
- 리포트의 `h2`, `h3`를 자동 수집한 목차 버튼

동작:

- 클릭 시 해당 섹션으로 smooth scroll
- IntersectionObserver로 현재 섹션 highlight
- 모바일에서는 목차를 상단 grid 형태로 표시

### 24.3 경영진 요약 카드

상단에 3개 카드를 표시한다.

| 카드 | 내용 |
|---|---|
| 핵심 요약 | 3줄 요약의 첫 번째 줄 |
| 주요 리스크 | 3줄 요약의 두 번째 줄 |
| 권고 조치 | 3줄 요약의 세 번째 줄 |

요약이 아직 생성 전이면 placeholder를 표시한다.

### 24.4 시각화 카드

Chart.js 기반 시각화 6개를 표시한다.

| 카드 | 데이터 |
|---|---|
| 검색 트렌드 (일별) | 네이버 데이터랩 최근 30일 line chart |
| 일자별 보도량 | 기사 날짜별 건수 bar chart |
| 논조 분포 | AI 리포트 내 🟢🟡🟠🔴 emoji count 기반 doughnut chart |
| 매체별 보도 비중 | 매체별 기사 수 doughnut chart |
| 연령대별 관심도 | 데이터랩 연령대별 bar chart |
| 리스크 키워드 | AI 리포트의 키워드/빈도 표 기반 tag cloud |

데이터가 없을 경우 차트 영역에 다음과 같은 빈 상태를 표시한다.

```text
데이터랩 데이터 없음
보도량 데이터 없음
매체 데이터 없음
연령대 데이터 없음
키워드 없음
```

### 24.5 리포트 영역

리포트 HTML이 있으면 즉시 표시한다.

리포트 HTML이 아직 없으면:

- spinner 표시
- `GET /api/report/<task_id>`를 2초 간격으로 polling
- 준비 완료 시 HTML 삽입
- Markdown 원본과 요약 텍스트를 hidden textarea에 저장
- 복사, 브리프 모달 버튼 활성화

### 24.6 브리핑 모달

`경영진 브리프` 버튼 클릭 시 modal overlay를 띄운다.

포함 내용:

- 회사명
- 기사 수
- RAG 검색 결과 수
- 분석 시점
- 상황 판단
- 핵심 리스크
- 즉시 권고
- AI 생성 초안 안내 문구
- 요약 복사 버튼

### 24.7 표 후처리

리포트 내 table은 다음을 적용한다.

- overflow-x wrapper로 모바일 가로 스크롤 지원
- 우선순위, 등급, 온도, 확률, 빈도 컬럼 기준 자동 정렬
- 위험/주의/긍정 키워드 색상 강조
- `🔴`, `🟠`, `🟡`, `🟢` emoji 색상 강조

### 24.8 인쇄

`window.print()`를 지원한다.

인쇄 시:

- nav, 목차, 버튼, chart 영역 숨김
- 리포트 본문 중심으로 흰 배경 출력

---

## 25. 문서 관리 화면 UI

`templates/proj3/documents.html`을 구현한다.

화면 구성:

- 상단 nav
  - 로고
  - 분석 화면으로 돌아가기 링크
- 페이지 헤더
  - 제목: `회사 자료 관리 (RAG)`
  - 설명 문구
- KPI row
  - 등록 문서 수
  - 벡터 청크 수
  - 등록 회사 수
- 문서 업로드 카드
  - drag & drop 스타일 파일 선택 영역
  - 관련 사업회사 select
  - 자료 분류 select
  - 업로드 버튼
- 저장된 문서 목록 카드
  - 문서별 아이콘
  - 파일명
  - 회사 badge
  - 분류 badge
  - 청크 수 badge
  - 삭제 버튼
- 문서가 없으면 empty state 표시

프론트엔드 동작:

- 파일 선택 시 파일명 표시
- dragenter/dragover 시 강조 스타일
- drop 시 file input에 파일 반영
- 삭제 전 `confirm('정말 삭제하시겠습니까?')`

---

## 26. 스타일 가이드

전체 UI는 다음 CSS 방향을 따른다.

컬러 토큰:

```css
:root {
    --bg: #0b1016;
    --surface: #111820;
    --surface2: #17212b;
    --surface3: #1d2935;
    --border: #2a3645;
    --text: #eef3f8;
    --dim: #9aa8b8;
    --muted: #708092;
    --accent: #3b82f6;
    --accent-strong: #2563eb;
    --success: #22c7a9;
    --warning: #f5b84b;
    --danger: #ef6f73;
}
```

공통 디자인 원칙:

- 카드 border-radius는 8px 이하
- 버튼에는 lucide icon 사용
- 업무용 대시보드처럼 밀도 있고 읽기 쉬운 정보 구조
- 과도한 hero, 장식용 blob, 마케팅형 레이아웃 금지
- 모바일에서 텍스트가 버튼 밖으로 넘치지 않게 처리
- 테이블은 모바일에서 가로 스크롤 가능
- 배경은 어두운 색상 중심이지만 시각화 색상은 blue, teal, amber, red를 균형 있게 사용

---

## 27. 예외 처리 조건

다음 예외 처리를 반드시 포함한다.

- 키워드가 비어 있으면 분석 시작하지 않고 메인 화면으로 이동
- 네이버 뉴스 API 실패 시 빈 문자열 반환
- 수집된 기사 본문이 하나도 없으면 작업 실패 처리
- 개별 기사 크롤링 실패는 전체 실패로 보지 않음
- 네이버 데이터랩 키가 없으면 데이터랩 차트만 빈 상태로 표시
- RAG 문서가 없어도 분석은 계속 진행
- Gemini/OpenAI API 키가 없거나 호출 실패 시 오류 메시지 반환
- PDF 파싱 실패 시 binary decode fallback 시도
- 업로드 파일 읽기 실패 시 오류 메시지 표시
- 지원하지 않는 파일 형식 업로드 시 오류 메시지 표시
- SQLite lock을 줄이기 위해 WAL, busy_timeout 적용
- 백그라운드 분석 중 예외가 발생해도 Flask 프로세스가 종료되지 않도록 처리

---

## 28. 실행 방법

README에 다음 내용을 포함한다.

### 28.1 공통 준비

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env`에 다음 값을 입력한다.

```text
OPENAI_API_KEY
GEMINI_API_KEY 또는 GOOGLE_API_KEY
NAVER_CLIENT_ID
NAVER_CLIENT_SECRET
NAVER_DATALAB_CLIENT_ID
NAVER_DATALAB_CLIENT_SECRET
```

### 28.2 macOS 로컬 실행

```bash
APP_HOST=127.0.0.1 APP_PORT=5001 python app.py
```

브라우저에서 접속:

```text
http://127.0.0.1:5001
```

### 28.3 Linux VPS 실행

```bash
export APP_DATA_DIR=/var/lib/posco-issue-ai
export FLASK_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
gunicorn --workers 2 --threads 4 --bind 0.0.0.0:5001 wsgi:app
```

VPS에서는 `APP_HOST=0.0.0.0` 또는 Gunicorn bind 주소 `0.0.0.0:5001`을 사용한다.

Nginx를 앞단에 둘 경우 Gunicorn은 내부 포트에만 열고 Nginx에서 리버스 프록시로 연결한다.

---

## 29. 핵심 개발 조건

- 포트는 기본값 `5001` 사용
- Flask app factory와 `wsgi.py` 모두 구현
- 작업 상태와 결과는 SQLite에 저장
- 분석은 백그라운드 thread로 실행
- 진행 화면은 polling 기반
- 결과 화면은 리포트 준비 전에도 먼저 열리고, `/api/report/<task_id>` polling으로 본문을 채움
- 네이버 뉴스 검색은 Naver Search API 사용
- 네이버 인링크 기사만 크롤링
- 기사 수집은 병렬 처리
- 네이버 데이터랩은 키가 있을 때만 사용
- RAG는 ChromaDB + Gemini embedding 사용
- RAG 문서 업로드, 목록, 삭제 기능 포함
- 회사별 컨텍스트를 AI 프롬프트에 반영
- 포스코홀딩스와 사업회사 분석 범위를 구분
- AI 리포트는 Markdown으로 생성하고 HTML로 변환
- 경영진 3줄 요약을 별도 생성
- 결과 화면에는 차트, 목차, 복사, 인쇄, 브리프 모달 포함
- 모바일 반응형 UI 구현
- 운영 배포를 위한 Gunicorn 실행 방법 포함

---

## 30. 최종 요청

위 요구사항에 따라 `proj3` 폴더 구조의 Flask 웹 애플리케이션 전체 코드를 작성해줘.

다음 조건을 반드시 만족해줘.

- 각 파일별 전체 코드를 모두 제공
- `requirements.txt` 포함
- `README.md` 포함
- `wsgi.py` 포함
- 설치 명령어 포함
- 로컬 실행 방법 포함
- Linux VPS 배포 실행 방법 포함
- Flask app factory 구현
- SQLite 기반 작업 상태 저장 구현
- 백그라운드 thread 분석 구현
- 네이버 뉴스 API 연동 코드 포함
- 네이버 인링크 기사 원문 크롤링 코드 포함
- 네이버 데이터랩 API 연동 코드 포함
- ChromaDB + Gemini embedding 기반 RAG 구현
- TXT/PDF/DOCX/MD 업로드 및 문서 삭제 기능 포함
- OpenAI 기반 AI 리포트 생성 코드 포함
- 경영진 3줄 요약 생성 코드 포함
- Markdown → HTML 변환 처리 포함
- 다크 대시보드 UI 포함
- Chart.js 기반 시각화 포함
- Lucide icon 기반 버튼 포함
- 모바일 반응형 UI 포함
- 진행률 표시 UI 포함
- 결과 리포트 polling UI 포함
- 경영진 브리프 모달 포함
- 복사 및 인쇄 기능 포함
- 예외 처리 포함
- 코드 전체를 바로 실행 가능한 수준으로 작성
