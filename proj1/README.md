# 네이버 기자 분석기 (POSCO PR 전용)

## 설치 및 실행

### 1. 패키지 설치
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 환경변수 확인
`.env` 파일에 아래 항목이 있어야 합니다:
```
GOOGLE_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.0-flash
```

### 3. 앱 실행
```bash
python app.py
```
브라우저에서 `http://localhost:5000` 접속

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
