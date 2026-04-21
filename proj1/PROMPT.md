# 네이버 기자 분석 웹앱 개발 프롬프트

## 개요
포스코 홍보 담당자가 네이버 뉴스 기자를 검색하고 기사를 분석하여 미팅 토킹포인트를 자동 생성하는 Flask 웹 애플리케이션 개발.

---

## 기술 스택
- **백엔드**: Python + Flask
- **크롤링**: Playwright (Chromium headless) + BeautifulSoup4
- **AI 분석**: Google Gemini API (`.env`의 `GOOGLE_API_KEY`, 모델: `gemini-2.0-flash`)
- **프론트엔드**: Bootstrap 5 (PC + 모바일 반응형)
- **포트**: 5001

---

## .env 파일 (기존 파일 사용)
```
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=change-this-secret
GOOGLE_API_KEY=<키값>
GEMINI_MODEL=gemini-2.0-flash
REQUEST_TIMEOUT=12
MAX_ARTICLES=30
```

---

## 파일 구조
```
proj1/
├── app.py
├── requirements.txt
├── .env
├── utils/
│   ├── __init__.py
│   ├── crawler.py
│   └── analyzer.py
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── progress.html
│   └── result.html
└── static/
    ├── css/style.css
    └── js/main.js
```

---

## 기능 요구사항

### 1. 사용자 입력
- 검색 폼: **매체명** + **기자명** 입력

### 2. 크롤링 — 네이버 기자 페이지

**매체 탐색**
- URL: `https://media.naver.com/journalists/whole?officeId=001`
- officeId는 `001`~`057`까지 존재하며 매체마다 페이지가 다름
- 001부터 057까지 순회하며 페이지 내 매체명 일치 여부 확인
- 매체명 감지 우선순위: `<title>` 태그 → `h1/h2/h3/strong` → CSS 클래스(`press/office/media/name`)

**기자 검색**
- 해당 매체 기자 목록 페이지는 **무한 스크롤** 방식
- **10회 스크롤**하며 기자명 탐색
- 매칭 우선순위: journalist URL + 이름 정확일치 → 포함 → 텍스트 포함

**기사 수집**
- 기자 페이지에서 `전체 기사` 탭 클릭 후 **5회 스크롤**하여 기사 목록 수집
- 수집 기사 중 **최신 20건**: 원문 수집 (관심분야·논조·키워드 분석용)
- 수집 기사 중 **포스코 관련 5건**: 제목 키워드 필터 후 원문 수집 (토킹포인트 생성용)
- 포스코 키워드: `포스코, POSCO, 포항제철, 포스코홀딩스, 포스코퓨처엠, 포스코인터내셔널, 포스코건설, 포스코케미칼`
- 기사 원문 선택자 (우선순위): `div#dic_area` → `div.newsct_article` → `div#articleBodyContents` → `article`

### 3. AI 분석 — Gemini 2회 분리 호출

**1차 호출**: 최신 기사 20건 → 아래 항목 분석
- 관심 분야 (3~5개)
- 기사 논조 (전체 요약, 특징, stance: 비판적/중립적/우호적)
- 최근 관심 키워드 (5~10개, 빈도: 높음/중간/낮음)

**2차 호출**: 포스코 관련 기사 5건 → 아래 항목 생성
- 포스코 보도 성향 (논조, 토픽, 요약)
- 토킹포인트 정확히 **5개** (제목, 내용 2~3문장, 활용 이유)
- 전반적인 미팅 전략
- 포스코 기사 없으면 최신 기사 기반으로 대체 생성
- 기사 본문 미수집 시 제목만으로도 분석

### 4. Flask 앱 구조
- 백그라운드 `threading.Thread`로 크롤링·분석 실행
- 진행 상황은 2초 간격 **폴링** 방식 (`/api/status/<job_id>`)
- 라우트: `GET /` → `POST /search` → `GET /progress/<id>` → `GET /result/<id>`

### 5. 결과 화면 — 4개 탭
| 탭 | 내용 |
|----|------|
| 종합 분석 | 관심 분야 / 기사 논조 / 최근 관심 키워드 |
| 최신 기사 | 최신 기사 20건 (제목·날짜·원문 링크) |
| 포스코 기사 | 포스코 관련 기사 5건 + 보도 성향 요약 |
| 토킹포인트 | 미팅 전략 + 토킹포인트 5개 |
