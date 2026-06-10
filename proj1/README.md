# 네이버 기자 분석 웹앱

`prompt.md` 요구사항을 바탕으로 만든 Flask 애플리케이션입니다.

## 실행

```powershell
python -B app.py
```

브라우저에서 프로젝트 루트(`pr/.env`)의 `FLASK_PORT` 값에 맞춰 접속합니다. 현재 설정은 `http://127.0.0.1:5003`입니다.

## 참고

- 프로젝트 루트(`pr/.env`)의 `OPENAI_API_KEY`, `OPENAI_MODEL`, `FLASK_PORT` 값을 사용합니다.
- 토킹 포인트의 최신 공개 이슈 검색은 OpenAI Responses API의 웹 검색 도구를 사용합니다.
- 기본 웹 검색 도구는 `OPENAI_WEB_SEARCH_TOOL=web_search`입니다. 기존 동작이 필요하면 `web_search_preview`로 바꿀 수 있습니다.
- 웹 검색 전용 모델을 분리하려면 `OPENAI_WEB_SEARCH_MODEL`, `OPENAI_WEB_SEARCH_FALLBACK_MODEL`을 설정합니다.
- Chromium이 설치되어 있지 않으면 아래 명령을 한 번 실행합니다.

```powershell
python -m playwright install chromium
```
