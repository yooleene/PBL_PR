# 통합 Flask 앱 리눅스 서버 배포/운영 매뉴얼

이 매뉴얼은 `pr` 폴더 하위의 `proj1`, `proj2`, `proj3`를 각각 따로 실행하지 않고,
루트의 `pr/app.py` 하나로 통합 실행하는 현재 구조 기준입니다.

접속 경로:

```text
/
/login
/proj1
/proj2
/proj3
```

운영 실행은 하나의 Gunicorn 프로세스와 하나의 Nginx 도메인 설정을 사용합니다.

---

## 1. SSH 접속

```bash
ssh root@183.111.227.182
```

root 비밀번호를 입력합니다.

---

## 2. 코드 파일 업로드

로컬 터미널에서 `pr` 폴더가 있는 상위 폴더로 이동한 뒤 실행합니다.

```bash
scp -r pr root@183.111.227.182:/root/
```

서버 기준 최종 경로는 다음과 같아야 합니다.

```text
/root/pr/app.py
/root/pr/auth.py
/root/pr/templates/
/root/pr/proj1/
/root/pr/proj2/
/root/pr/proj3/
/root/pr/requirements.txt
```

기존 서버 폴더에 파일이 남아 충돌하는 경우에는 백업 후 전체 교체하는 편이 안전합니다.

```bash
mv /root/pr /root/pr_backup_$(date +%Y%m%d_%H%M%S)
scp -r pr root@183.111.227.182:/root/
```

---

## 3. `.env` 파일 관리

현재 통합 구조에서는 `.env`가 각 프로젝트 폴더가 아니라 루트에 있어야 합니다.

권한 설정:

```bash
chmod 600 /root/pr/.env
ls -l /root/pr/.env
```

정상 예시:

```bash
-rw------- 1 root root 1200 May 15 10:00 /root/pr/.env
```

HTTPS 적용 후에는 세션 쿠키 보호를 위해 다음으로 변경하는 것을 권장합니다.

```env
SESSION_COOKIE_SECURE=true
```

---

## 4. Python 가상환경 및 패키지 설치

서버에서 실행합니다.

```bash
cd /root/pr
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

`proj1`이 Playwright를 사용하므로 Chromium과 리눅스 의존성을 설치합니다.

```bash
python3 -m playwright install --with-deps chromium
```

가상환경 종료:

```bash
deactivate
```

---

## 5. 최초 테스트 실행

서버 터미널에서 먼저 직접 실행해 import 오류와 `.env` 설정을 확인합니다.
`python3 app.py` 직접 실행 시 기본 포트는 `5001`입니다(맥 로컬 개발 기준).
운영 gunicorn은 `5000`을 사용하므로, 테스트도 운영 포트(5000)에 맞추려면 아래처럼 포트를 지정해 실행합니다.

```bash
cd /root/pr
source venv/bin/activate
FLASK_PORT=5000 python3 app.py
```

정상 실행 시 내부 포트에서 Flask가 실행됩니다.

```text
http://127.0.0.1:5000
```

다른 SSH 터미널에서 확인:

```bash
curl -I http://127.0.0.1:5000/login
curl -I http://127.0.0.1:5000/proj1
curl -I http://127.0.0.1:5000/proj2
curl -I http://127.0.0.1:5000/proj3
```

`/proj1`, `/proj2`, `/proj3`는 로그인 전이면 `/login`으로 리다이렉트되는 것이 정상입니다.

테스트 실행 종료는 실행 중인 터미널에서 `Ctrl + C`를 누릅니다.

---

## 6. 운영 백그라운드 실행(systemd)

통합 구조에서는 앱별 서비스를 여러 개 만들지 않고 하나의 서비스만 만듭니다.

서비스명 예시:

```text
pr_unified
```

서비스 파일 생성:

```bash
cat >/etc/systemd/system/pr_unified.service <<'EOF'
[Unit]
Description=PR Unified Flask Gunicorn Service
After=network.target

[Service]
User=root
WorkingDirectory=/root/pr
EnvironmentFile=/root/pr/.env
ExecStart=/root/pr/venv/bin/gunicorn -w 1 --timeout 180 --graceful-timeout 30 -b 127.0.0.1:5000 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
```

적용 및 실행:

```bash
systemctl daemon-reload
systemctl enable pr_unified
systemctl start pr_unified
systemctl status pr_unified
journalctl -u pr_unified -n 50 --no-pager
```

현재 `proj1`은 분석 진행 상태를 메모리 `JOBS` 딕셔너리에 저장합니다.
따라서 Redis 같은 외부 저장소로 바꾸기 전에는 Gunicorn worker를 `-w 1`로 유지하는 것이 안전합니다.

---

## 7. Nginx 도메인 연결

Nginx 설정 파일 생성:

```bash
cat >/etc/nginx/sites-available/pr_unified <<'EOF'
server {
    listen 80;
    server_name pr.wxpbl.kr;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 180s;
        proxy_send_timeout 180s;
        proxy_read_timeout 180s;
    }
}
EOF
```

적용:

```bash
ln -sf /etc/nginx/sites-available/pr_unified /etc/nginx/sites-enabled/pr_unified
nginx -t
systemctl restart nginx
```

---

## 8. HTTPS 적용 권장(현재는 사용 안함)

도메인 연결 후 Certbot을 사용할 수 있습니다.

```bash
apt update
apt install -y certbot python3-certbot-nginx
certbot --nginx -d pr.wxpbl.kr
```

HTTPS 적용 후 `/root/pr/.env`에서 다음 값을 권장합니다.

```env
SESSION_COOKIE_SECURE=true
```

변경 후 재시작:

```bash
systemctl restart pr_unified
systemctl restart nginx
```

---

## 9. 소스 코드 수정 시 업데이트

통합 구조에서는 `proj1` 폴더만 올리면 부족할 수 있습니다.
루트의 `app.py`, `auth.py`, `templates/`, `requirements.txt`도 함께 바뀔 수 있기 때문입니다.

가장 안전한 방식은 전체 `pr` 폴더를 다시 올리는 것입니다.
로컬 터미널에서 `pr` 폴더가 있는 상위 폴더로 이동한 뒤 실행합니다.

로컬 터미널:

```bash
scp -r pr root@183.111.227.182:/root/
```

서버에서 패키지 변경 반영 및 재시작:

```bash
cd /root/pr
source venv/bin/activate
pip install -r requirements.txt
systemctl restart pr_unified
systemctl status pr_unified
journalctl -u pr_unified -n 50 --no-pager
```

venv로 들어간 상태이면 아래처럼 실행해서 빠져 나옵니다.

```bash
deactivate
```

`.env`는 서버의 실제 비밀값 파일이므로 로컬 예시 파일로 덮어쓰지 않도록 주의합니다.
업로드 후 권한을 다시 확인합니다.

```bash
chmod 600 /root/pr/.env
```

---

## 10. 서비스 중지 및 초기화

실행 중인 Gunicorn 확인:

```bash
ps -ef | grep gunicorn
```

systemd 서비스 확인:

```bash
systemctl | grep pr_
```

서비스 중지: pr_unified 는 서비스 이름

```bash
systemctl stop pr_unified.service
```

현재 등록된 사비스명 확인:
```bash
ls /etc/systemd/system/ | grep pr_
```

자동 시작 해제:

```bash
systemctl disable pr_proj1.service
systemctl disable pr_proj2.service
systemctl disable pr_proj3.service
```

포트 확인:

```bash
ss -tulpn | grep 5000
```

아무것도 나오지 않으면 해당 포트는 사용 중이 아닙니다.

폴더 삭제 전에는 필요한 DB와 업로드 파일을 먼저 백업합니다.

```bash
cp -a /root/pr/proj2/instance /root/proj2_instance_backup_$(date +%Y%m%d_%H%M%S)
cp -a /root/pr/proj3/data /root/proj3_data_backup_$(date +%Y%m%d_%H%M%S)
```

전체 폴더 삭제:

```bash
rm -rf /root/pr
```

서비스 파일 삭제:

```bash
rm -f /etc/systemd/system/pr_unified.service
systemctl daemon-reload
```

마지막 확인:

```bash
systemctl | grep pr_
ps -ef | grep gunicorn
ss -tulpn | grep 5000
```

---

## 11. 운영 점검 체크리스트

배포 후 다음을 확인합니다.

```bash
curl -I http://127.0.0.1:5000/login
curl -I http://127.0.0.1:5000/
curl -I http://127.0.0.1:5000/proj1
curl -I http://127.0.0.1:5000/proj2
curl -I http://127.0.0.1:5000/proj3
systemctl status pr_unified
journalctl -u pr_unified -n 100 --no-pager
nginx -t
```

로그인 전에는 `/`, `/proj1`, `/proj2`, `/proj3`가 `/login`으로 이동해야 정상입니다.

관리자 계정으로 확인할 기능:

```text
/proj2 데이터 추출
/proj2 추출 후 저장
/proj2 수정/삭제/CSV 업로드
```

일반 사용자 계정으로 확인할 기능:

```text
/proj2 조회 가능
/proj2 데이터 추출/저장/수정/삭제 버튼 비활성화
/proj2 admin 전용 URL 직접 접근 시 403 차단
```

---

## 12. `/proj2` 데이터 추출 500 오류 점검

### 원인 (확인됨)

데이터 추출 버튼의 `Internal Server Error`는 코드 버그가 아니라 **타임아웃**이었습니다.
Gemini 검색 grounding 호출이 길어지면, 요청을 처리하던 Gunicorn 워커가
`--timeout` 시간을 넘겨 강제 종료(`WORKER TIMEOUT` → `SystemExit`)되면서 500이 납니다.
Gemini가 빨리 응답하면 성공하므로 "가끔 잘 됨" 증상이 나타납니다.
로컬(Flask 개발 서버)은 요청 타임아웃이 없어 항상 정상 동작합니다.

로그에서 다음이 보이면 이 케이스입니다.

```bash
journalctl -u pr_unified -n 100 --no-pager
# [CRITICAL] WORKER TIMEOUT (pid:...)
# File ".../proj2/app.py", line ..., in call_gemini_grounded
#     response = client.models.generate_content(...)
# SystemExit: 1
```

### 적용된 해결 (현재 코드)

1. **Gemini 호출 자체에 타임아웃**을 걸어, gunicorn이 워커를 죽이기 전에 정상 예외로
   떨어지게 했습니다(`GEMINI_TIMEOUT_SECONDS`, 기본 150초). 그러면 500 대신
   `"주요인사발언 추출 실패: ..."` 안내 메시지가 나가고 워커는 살아 있습니다.
2. **추출을 백그라운드 스레드로 분리**했습니다. 버튼을 누르면 즉시 진행 페이지로
   이동해 폴링하고, 완료되면 기존 확인/저장 화면으로 자동 전환됩니다. 요청 스레드가
   Gemini 응답을 기다리지 않으므로 워커 타임아웃이 발생하지 않습니다.
   (proj1과 같은 단일 워커 `-w 1` 전제에서 안전합니다.)

### .env 옵션

`/root/pr/.env`에서 Gemini 호출 제한 시간을 조정할 수 있습니다.
반드시 gunicorn `--timeout`(180)보다 **작게** 두세요.

```env
GEMINI_TIMEOUT_SECONDS=150
```

API 키도 함께 확인합니다.

```bash
grep -E '^(GOOGLE_API_KEY|GEMINI_MODEL|GEMINI_TIMEOUT_SECONDS)=' /root/pr/.env | sed -E 's/=.*/=설정됨/'
```

### 배포 주의

`proj2`는 이제 `proj1`/`proj3`와 동일하게 **블루프린트 단일 소스**(`bp` + `create_app()`)로
정리되어, 루트 통합 앱이 그대로 import합니다. 따라서 9번 항목대로 `pr` 폴더 전체를
`scp`로 올려도 안전합니다. (이전에는 `proj2/app.py`에 `bp`가 없어 통합 앱이 import 단계에서
죽을 수 있었습니다.)

코드 갱신 후 재시작:

```bash
cd /root/pr
source venv/bin/activate
pip install -r requirements.txt
systemctl restart pr_unified
journalctl -u pr_unified -n 50 --no-pager
```

> 선택: 여러 사용자가 동시에 쓰거나 진행 페이지 폴링을 더 매끄럽게 하려면
> Gunicorn을 스레드 워커로 바꿀 수 있습니다(메모리를 공유하므로 proj1 JOBS도 안전).
> `ExecStart`의 `-w 1`을 `-w 1 -k gthread --threads 4`로 변경하면 됩니다.
