# 네이버 기자 분석기 (POSCO PR 전용)

## 공통 준비

### 1. 코드 업로드 후 프로젝트 진입
```bash
cd /path/to/proj1
```

### 2. 가상환경 및 패키지 설치
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

리눅스 서버에서 Playwright 시스템 패키지까지 한 번에 설치하려면:
```bash
python -m playwright install --with-deps chromium
```

### 3. 환경변수 설정
`.env` 파일을 만들고 최소 아래 항목을 채웁니다. 기본값 예시는 [.env.example](/Users/yooleene/Documents/LAB/PBL/pr/proj1/.env.example:1)에 있습니다.

```
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4.1-mini
SECRET_KEY=change-this-secret-key
FLASK_HOST=0.0.0.0
FLASK_PORT=5001
FLASK_DEBUG=true
```

## macOS 로컬 실행
```bash
python app.py
```
브라우저에서 `http://localhost:5001` 접속

## Linux 서버 실행
개발 확인용:
```bash
python app.py
```

배포용 권장:
```bash
gunicorn -b 0.0.0.0:5001 app:app
```

참고:
- 현재 작업 상태는 메모리 `JOBS`에 저장됩니다.
- 그래서 운영 환경에서는 `gunicorn`을 `-w 1` 단일 워커로 쓰거나, 추후 Redis/DB로 분리하는 편이 안전합니다.

---

## 사용법
1. 매체명 입력 (예: 조선일보)
2. 기자명 입력 (예: 홍길동)
3. '기자 분석 시작' 클릭
4. 2~5분 대기 후 결과 확인

## 분석 결과
- 관심 분야 / 기사 논조 / 최근 키워드
- 최신 기사 최대 20건
- 포스코 관련 기사 최대 5건
- 포스코 홍보 담당자용 미팅 토킹포인트 5개
