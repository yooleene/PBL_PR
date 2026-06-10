# 이슈 분석 AI

macOS 로컬 개발과 Linux VPS 호스팅을 모두 지원하는 Flask 앱입니다.

## 공통 준비

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

설정값은 프로젝트 루트(`pr/.env`)의 `OPENAI_API_KEY`, `GEMINI_API_KEY`, `NAVER_*` 값을 사용합니다.

## macOS에서 실행

```bash
APP_HOST=127.0.0.1 APP_PORT=5001 python app.py
```

브라우저에서 `http://127.0.0.1:5001`로 접속합니다.

## Linux VPS에서 실행

VPS에서는 외부 접속을 위해 `APP_HOST=0.0.0.0`을 사용하거나 Gunicorn의 bind 주소를 `0.0.0.0`으로 지정합니다.

```bash
export APP_DATA_DIR=/var/lib/posco-issue-ai
export FLASK_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
gunicorn --workers 2 --threads 4 --bind 0.0.0.0:5001 wsgi:app
```

Nginx를 앞단에 둘 경우 Gunicorn은 내부 포트에만 열고 Nginx에서 리버스 프록시로 연결합니다.

## 설정값

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `APP_HOST` | `127.0.0.1` | `python app.py` 실행 시 바인딩 주소 |
| `APP_PORT` | `5001` | 앱 포트 |
| `APP_DEBUG` | `false` | Flask 디버그 모드 |
| `FLASK_SECRET_KEY` | 개발용 기본값 | 운영 환경에서는 반드시 변경 |
| `APP_DATA_DIR` | `./data` | 업로드, ChromaDB, 작업 DB 기본 저장 위치 |
| `APP_UPLOAD_DIR` | `$APP_DATA_DIR/uploads` | 업로드 파일 저장 위치 |
| `APP_CHROMA_DIR` | `$APP_DATA_DIR/chroma_db` | ChromaDB 저장 위치 |
| `APP_TASK_DB` | `$APP_DATA_DIR/tasks.sqlite3` | 분석 진행상태와 결과 저장 SQLite 파일 |
| `APP_USER_AGENT` | Linux Chrome UA | 네이버 기사 본문 요청 User-Agent |

## 운영 메모

분석 진행상태와 결과는 SQLite에 저장되므로 Gunicorn 다중 워커에서도 진행 화면과 결과 화면이 같은 상태를 읽습니다. ChromaDB와 업로드 파일은 `APP_DATA_DIR` 아래에 저장되며, Linux 서비스 계정이 해당 디렉터리에 쓰기 권한을 가져야 합니다.
