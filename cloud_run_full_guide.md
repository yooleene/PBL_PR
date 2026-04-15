# Cloud Run + Secret Manager 완전 실습 가이드 (초보자용 전체 버전)

## 🚀 목표

Python AI Agent 웹앱을\
Cloud Shell만 사용해서\
Cloud Run에 배포하고\
Secret Manager까지 연결

------------------------------------------------------------------------

## 0. 전체 흐름

1.  Google Cloud 프로젝트 생성\
2.  결제 연결\
3.  Cloud Shell 실행\
4.  소스코드 업로드\
5.  Secret 생성\
6.  Cloud Run 배포\
7.  URL 접속

------------------------------------------------------------------------

## 1. Google Cloud 프로젝트 생성

### 1-1. 콘솔 접속

https://console.cloud.google.com

### 1-2. 프로젝트 생성

-   상단 → 프로젝트 선택 → 새 프로젝트

### 1-3. 입력

-   이름: my-ai-agent

### 1-4. 프로젝트 선택

상단에서 생성한 프로젝트 선택

------------------------------------------------------------------------

## 2. 결제 연결

-   좌측 메뉴 → 결제
-   결제 계정 연결

------------------------------------------------------------------------

## 3. Cloud Shell 실행

-   우측 상단 터미널 아이콘 클릭

------------------------------------------------------------------------

## 4. 소스코드 업로드

### *** 쉘 우측 상단의 점세개 메뉴를 클릭하고 업로드 메뉴 누르면 폴더 업로드 가능
-------------------
### *** 압축해서 업로드 하는 방법
-------------------
### 1) 로컬에서 zip 압축

my-agent-app.zip

### 2) Cloud Shell 업로드

### 3) 압축 해제

``` bash
unzip my-agent-app.zip
cd my-agent-app
ls
```

------------------------------------------------------------------------

## 5. 코드 필수 조건 - 바이브 코딩시 google cloud run에서 가능하도록 수정 요청

``` python
import os
app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
```

------------------------------------------------------------------------

## 6. requirements.txt 파일은 반드시 있어야 함


------------------------------------------------------------------------

## 7. Secret Manager - 환경파일 안전하도록 설정(api 키 등)

### 7-1. Secret 생성

``` bash
echo -n "sk-xxxx" | gcloud secrets create openai-api-key --data-file=-
```

### 7-2. 여러 개 생성 - 메모장에서 정리 후 쉘에서 한번에 실행

``` bash
echo -n "sk-openai" | gcloud secrets create openai-api-key --data-file=-
echo -n "postgres://..." | gcloud secrets create db-url --data-file=-
echo -n "redis://..." | gcloud secrets create redis-url --data-file=-
```

### 7-3. Secret Manager API 활성화 

``` bash
gcloud services enable secretmanager.googleapis.com
```
그리고 1~3분 정도 기다린 뒤, 다시 배포하면 됨. API를 방금 켠 경우 시스템에 반영되기까지 잠시 걸릴 수 있음.
------------------------------------------------------------------------

## 8. Cloud Run 배포

``` bash
gcloud run deploy pbl-pr-proj1 \
  --source . \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --set-secrets GOOGLE_API_KEY=google-api-key:latest,DB_URL=db-url:latest
```

------------------------------------------------------------------------

## 9. Python에서 사용

``` python
import os
api_key = os.environ.get("OPENAI_API_KEY")
```

------------------------------------------------------------------------

## 10. 운영 방법

### 코드 변경

``` bash
gcloud run deploy pbl-pr-proj1 --source .
```

### 키 변경

``` bash
echo -n "새키" | gcloud secrets versions add openai-api-key --data-file=-
```

### Secret 추가

``` bash
gcloud run deploy my-ai-agent --source . --set-secrets A=...,B=...
```

------------------------------------------------------------------------

## 11. 핵심 개념

-   코드 변경 → 재배포 필요\
-   Secret 변경 → 재배포 필요 없음\
-   Secret 추가 → 재배포 필요

------------------------------------------------------------------------

## 12. 구조 이해

    [Secret Manager]
       ↓
    [Cloud Run 환경변수]
       ↓
    [Python 코드]

------------------------------------------------------------------------

## 13. 초보자 실수

-   requirements.txt 없음\
-   localhost 사용\
-   PORT 미사용\
-   Secret 오타\
-   폴더 위치 오류

------------------------------------------------------------------------

## 14. 한 줄 정리

Cloud Shell → 코드 업로드 → Secret → deploy 끝
