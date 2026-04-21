# 네이버 기자 분석 - 사용법

## 설치 및 실행

### 2. 모든 코드를 다운 받아서 로컬에 저장

### 1. 패키지 설치 - 프로젝트 폴더(proj1) 터미널에서 실행
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 환경변수 확인
`.env` 파일에 아래 항목이 있어야 합니다: your_gemini_api_key를 제미나이 api key로 변경하세요
```
GOOGLE_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
```

### 3. 앱 실행 - 프로젝트 폴더(proj1) 터미널에서 실행
```bash
python app.py
```
브라우저에서 `http://localhost:5001` 접속 : url은 실생시 나오는 터미널에 있는 것을 복사해서 사용하세요

