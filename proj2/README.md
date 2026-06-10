# 정부 안전/노동 주요인사 발언 및 중대재해 분석 웹앱

Flask 기반 웹앱입니다. OpenAI Responses API의 `web_search` 도구로 기간별 데이터를 수집하고, OpenAI API로 종합분석과 당사 사고 대응방향을 생성합니다.

## 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

접속 주소:

```text
http://localhost:5001
```

5001 포트가 이미 사용 중이면 다음처럼 임시 포트를 지정할 수 있습니다.

```bash
PORT=5002 python app.py
```

## 설정

프로젝트 루트(`pr/.env`) 파일의 값을 사용합니다.

- `OPENAI_API_KEY`: OpenAI API 키
- `OPENAI_MODEL`: 기본값 `gpt-4o-mini`
- `OPENAI_WEB_SEARCH_MODEL`: 기본값 `gpt-4.1-mini`
- `OPENAI_WEB_SEARCH_CONTEXT_SIZE`: `low`, `medium`, `high` 중 하나. 기본값 `medium`
- `OPENAI_SPEECH_SEARCH_FALLBACK_QUERIES`: 주요인사발언 0건 반환 시 추가 검색어 수. 기본값 `8`
- `OPENAI_SPEECH_SEARCH_FALLBACK_WORKERS`: 주요인사발언 추가 검색 병렬 수. 기본값 `3`
- `SECRET_KEY`: Flask 세션 키

## 저장 데이터

SQLite DB는 `instance/safety_labor.db`에 생성됩니다.

- 주요인사발언: 주요인사발언 탭에서 기간별 데이터 추출 후 담당자 저장, CSV 업로드 누적 저장, 앱에서 수정/삭제, `speeches.csv` 다운로드
- 중대재해사례: 중대재해사례 탭에서 기간별 데이터 추출 후 담당자 저장, CSV 업로드 누적 저장, 앱에서 수정/삭제, 사과문 입력/수정, `incidents.csv` 다운로드
- 데이터검색: 저장된 주요인사발언, 중대재해사례, 종합분석, 당사사고 대응, 수집 이력 데이터를 자연어로 검색하고 답변 생성
- 종합분석: 버튼 클릭 시 OpenAI API로 생성 후 저장
- 기사 링크: OpenAI `web_search` 출처 URL을 저장하고, 기존 redirect URL은 실제 원문 URL로 보정하며 보정 불가 시 깨진 링크를 노출하지 않음
- 당사사고 대응방향: 재해내용 입력 시 사과문과 대응방향 생성, 담당자 검토/수정 후 저장
