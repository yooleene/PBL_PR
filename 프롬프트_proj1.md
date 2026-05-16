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
- 매체명 입력 시 고정 매핑된 officeId의 기자 목록 URL로 바로 이동
- 지원 매체: `연합뉴스(001)`, `프레시안(002)`, `뉴시스(003)`, `한국경제TV(004)`, `국민일보(005)`, `미디어오늘(006)`, `일다(007)`, `머니투데이(008)`, `매일경제(009)`, `서울경제(011)`, `연합인포맥스(013)`, `파이낸셜뉴스(014)`, `한국경제(015)`, `헤럴드경제(016)`, `이데일리(018)`, `MBN(019)`, `동아일보(020)`, `문화일보(021)`, `세계일보(022)`, `조선일보(023)`, `매경이코노미(024)`, `중앙일보(025)`, `한국일보(026)`, `한겨레(028)`, `디지털타임스(029)`, `전자신문(030)`, `아이뉴스24(031)`, `경향신문(032)`, `주간경향(033)`, `스포츠서울(034)`, `한겨레21(036)`, `주간동아(037)`, `The Korea Herald(044)`, `오마이뉴스(047)`, `MBC Sports+(049)`, `한경비즈니스(050)`, `YTN(052)`, `SBS(055)`, `KBS(056)`, `MBC(057)`, `JUMPBALL(065)`, `스포츠조선(076)`, `노컷뉴스(079)`, `서울신문(081)`, `부산일보(082)`, `제주일보(084)`, `내일신문(086)`, `매일신문(088)`, `연합뉴스TV(091)`, `ZDNet Korea(092)`, `SBS Biz(096)`
- 미지원 매체명 입력 시 지원 매체 목록을 포함한 오류 메시지 표시

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

**2차 호출**: 최신 기사 20건 + 포스코 관련 기사 5건 → 아래 항목 생성
- 포스코 보도 성향 (논조, 토픽, 요약)
- 토킹포인트 정확히 **5개** (제목, 내가 기자에게 직접 말하는 1인칭 대화 시나리오 100자 이내, 활용 이유)
- 전반적인 미팅 전략
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



아래는 추가 수정 프롬프트임
-------------------------------------------
https://media.naver.com/journalists/whole?officeId=001
___________________________________________________
위 주소는 네이버 기자 정보를 모아놓은 기자홈이야.
officeId=001의 키값은 매체별 페이지를 분류해 놓은건데,
001부터 099까지 네가 직접 확인하고 매체명을 추출해줘




**매체 탐색**
- URL: `https://media.naver.com/journalists/whole?officeId={officeId}`
- 입력 매체명에 매핑된 officeId 값으로 특정 매체의 기자 목록 페이지에 바로 접근
_____________________________________________________________
위와 같이 매체를 탐색하고 있는데, 다음과 같이 매체 탐색 과정을 변경하려고 해.
officeId의 값에 따라 특정 매체의 페이지에 바로 접근해거 기자를 탐색해줘.
아래에는 officeId 값과 매체명이야.
officeId=001 : 연합뉴스
officeId=002 : 프레시안
officeId=003 : 뉴시스
officeId=004 : 한국경제TV
officeId=005 : 국민일보
officeId=006 : 미디어오늘
officeId=007 : 일다
officeId=008 : 머니투데이
officeId=009 : 매일경제
officeId=011 : 서울경제
officeId=013 : 연합인포맥스
officeId=014 : 파이낸셜뉴스
officeId=015 : 한국경제
officeId=016 : 헤럴드경제
officeId=018 : 이데일리
officeId=019 : MBN
officeId=020 : 동아일보
officeId=021 : 문화일보
officeId=022 : 세계일보
officeId=023 : 조선일보
officeId=024 : 매경이코노미
officeId=025 : 중앙일보
officeId=026 : 한국일보
officeId=028 : 한겨레
officeId=029 : 디지털타임스
officeId=030 : 전자신문
officeId=031 : 아이뉴스24
officeId=032 : 경향신문
officeId=033 : 주간경향
officeId=034 : 스포츠서울
officeId=036 : 한겨레21
officeId=037 : 주간동아
officeId=044 : The Korea Herald
officeId=047 : 오마이뉴스
officeId=049 : MBC Sports+
officeId=050 : 한경비즈니스
officeId=052 : YTN
officeId=055 : SBS
officeId=056 : KBS
officeId=057 : MBC
officeId=065 : JUMPBALL
officeId=076 : 스포츠조선
officeId=079 : 노컷뉴스
officeId=081 : 서울신문
officeId=082 : 부산일보
officeId=084 : 제주일보
officeId=086 : 내일신문
officeId=088 : 매일신문
officeId=091 : 연합뉴스TV
officeId=092 : ZDNet Korea
officeId=096 : SBS Biz
* 매체명을 입력하면 위에 있는 officeId 값의 주소로 바로 이동해서 기자를 찾아줘.
