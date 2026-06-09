현재 `pr` 폴더 하위에는 Flask로 개발된 여러 개의 앱(proj1, proj2, proj3)이 각각
독립적으로 실행되고 있음.

========================
목표
========================
보안성과 운영 효율성을 위해 다중 Flask 앱을 하나의 Flask 애플리케이션으로 통합하고 싶음.
기존 앱의 독립성은 유지하되 운영 시 하나의 프로세스로 실행되도록 개선해줘.
Flask Blueprint 구조로 proj1/proj2/proj3을 모듈화해줘.

★ 추가 핵심: 통합 후 Linux VPS(gunicorn+nginx)에 올렸을 때, proj2처럼 외부 LLM(예: Gemini)
  호출이 오래 걸리는 기능에서 gunicorn 워커 타임아웃으로 인한 Internal Server Error(500)가
  "가끔" 발생하는 문제를 처음부터 구조적으로 방지해야 함.
  (로컬 Flask 개발서버는 요청 타임아웃이 없어 정상이지만, 서버 gunicorn은 --timeout 초과 시
   워커를 강제 종료(SystemExit)시켜 500이 난다.)

========================
핵심 요구사항
========================

1. Flask 앱 통합
- proj1/proj2/proj3을 하나의 Flask 앱으로 통합, 운영 시 단일 프로세스 실행
- Flask Blueprint 기반, 각 프로젝트는 /proj1, /proj2, /proj3 경로로 접근
- Windows/macOS 로컬 개발과 Linux VPS 호스팅 모두 지원

2. 독립 실행과 통합 실행 모두 고려
- 각 proj는 단독 실행도 가능(`python projN/app.py`), 운영은 통합(`python app.py` / gunicorn app:app)
- 각 projN/app.py는 반드시 `bp = Blueprint("projN", __name__, template_folder="templates",
  static_folder="static")` + `create_app()` 팩토리 + `app = create_app()` 형태로 통일.
  → 루트 통합 앱이 `from projN.app import bp` 로 import 되어야 하며, import 단계에서
    실패하지 않아야 함(모듈 레벨 `app=Flask(...)`+`@app.*` 만 있는 구조는 금지).
- 모든 `@app.*` → `@bp.*`, 모든 `url_for("x")` → `url_for("projN.x")`,
  `app.jinja_env.globals[...]` → `bp.add_app_template_global(...)`.
- 템플릿은 templates/projN/ 하위로 네임스페이스화(루트 templates/index.html과 충돌 방지),
  `render_template("projN/파일.html")` 형태로 호출, 정적파일은 `url_for('projN.static', ...)`.

3. 메인 페이지 구성
- 기존 pr/index.html 디자인 유지, 로그인 후 접근 가능한 메인으로 사용
- proj1/2/3 이동 버튼/메뉴, 클릭 시 새 창/새 탭으로 열림(target="_blank" 또는 window.open)
- 새 창에서도 Flask session 유지로 로그인 공유, 비로그인 접근 시 /login으로 이동

4. 로그인 필수
- 메인/모든 프로젝트 페이지는 로그인 후만 접근. /, /proj1~3 직접 입력해도 비로그인이면 /login

5. 로그인 기능
- admin/user 계정 구분, 로그인 시 session 저장, 상태 유지, 로그아웃 포함

6. 권한 관리
- admin/user 권한 명확 구분, login_required / admin_required 데코레이터 구조

7. proj2 권한 조건
- proj2의 데이터 추출/저장 기능은 admin만. user는 조회만(추출/저장 버튼 비활성+서버 라우트에서도 차단)
- URL 직접 접근도 admin 아니면 차단(버튼 숨김만으로 보안 처리 금지)
- ★ 이 admin 전용 "데이터 추출"은 외부 LLM(Gemini) 호출이 길어 10번 요구사항(백그라운드화)의
  주 대상이다.

8. 환경 변수 관리
- 모든 계정/설정은 pr/.env 에서 관리, 비밀번호/SECRET_KEY 하드코딩 금지
- .env 예시:
  ADMIN_ID, ADMIN_PASSWORD, USER_ID, USER_PASSWORD, SECRET_KEY, FLASK_ENV, FLASK_DEBUG,
  GOOGLE_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT_SECONDS

9. 보안 강화
- Flask session 인증, .env 로딩, .gitignore에 .env 포함, 모든 내부 라우트 로그인 검증,
  admin 기능은 서버 라우트에서도 권한 검증

★10. 장시간 외부 호출(LLM/크롤링)의 서버 타임아웃 방지 (필수)
  (1) 외부 LLM 클라이언트에 환경변수 기반 타임아웃을 건다.
     - 예: GEMINI_TIMEOUT_SECONDS(기본 150)를 ms로 변환해 genai.Client(..., 
       http_options=types.HttpOptions(timeout=...)) 로 적용.
     - 값은 반드시 gunicorn --timeout 보다 작게(예: 150 < 180). 그래야 워커가 죽기 전에
       정상 예외로 떨어져 기존 try/except가 사용자 안내(flash)로 처리한다.
  (2) 오래 걸리는 추출/분석은 요청 스레드에서 직접 실행하지 말고 백그라운드 스레드로 분리한다.
     - proj1과 동일한 패턴 사용: 메모리 JOBS 딕셔너리 + threading + uuid.
     - 추출 버튼 → job 생성 후 즉시 "진행 페이지"로 redirect.
     - 진행 페이지는 status JSON 엔드포인트를 2초 간격으로 폴링 → done/error면 결과 페이지로 이동.
     - 결과 페이지는 기존 "확인 후 저장" 화면을 그대로 재사용(추출 결과를 pending 컨텍스트로 렌더).
     - 라우트 예: POST /projN/extract(enqueue) , GET /projN/extract/progress/<id>(진행) ,
       GET /projN/extract/status/<id>(JSON) , GET /projN/extract/result/<id>(완료 렌더).
     - 효과: 요청 워커가 LLM 응답을 기다리지 않으므로 워커 타임아웃이 구조적으로 불가능.
  (3) 운영 전제: gunicorn 단일 워커(-w 1)에서 in-memory JOBS가 동작하도록 유지하거나,
     동시성이 필요하면 메모리를 공유하는 스레드 워커(-k gthread --threads N)를 쓴다.
     (-w 2 이상으로 늘리려면 JOBS를 Redis 등 외부 저장소로 옮겨야 함을 명시.)
  (4) 이 원칙은 proj2뿐 아니라 외부 LLM/크롤링을 호출하는 모든 proj(향후 proj4/5 포함)에 적용.

========================
원하는 결과물
========================
전체 구조와 실제 적용 가능한 예시 코드를 포함해서 제안해줘.

1. 최종 폴더 구조
2. 통합 Flask 앱 구조 / 3. Blueprint 적용 방식 / 4. 로그인 처리 구조
5. session 인증 예시 / 6. admin 권한 처리 예시 / 7. proj2 admin·user 권한 차등 예시
8. .env 예시 / 9. .gitignore 예시 / 10. requirements.txt 예시(google-genai, gunicorn 포함)
11. 통합 app.py 예시 / 12. auth 라우팅 예시 / 13. proj1/2/3 라우팅 예시
14. 기존 index.html을 templates로 이동해 쓰는 방법 / 15. 메뉴 버튼 연결 / 16. 새 창 열기
17. 비로그인 직접 URL 접근 차단 / 18. 실행 방법
19. 기존 개별 app.py를 Blueprint 구조로 이전하는 단계별 방법
★20. 외부 LLM 클라이언트 타임아웃 설정 예시(환경변수 기반, gunicorn timeout과의 관계 설명)
★21. 백그라운드 추출 작업(JOBS+스레드)과 진행 페이지 폴링 예시(status/result 라우트 + 진행 템플릿)
★22. gunicorn/nginx 운영 설정 예시(-w 1 --timeout 180, nginx proxy_read_timeout 180s,
     GEMINI_TIMEOUT_SECONDS < gunicorn --timeout 관계)

========================
검증
========================
- `import app`(통합 앱) 성공, 각 proj 엔드포인트 전부 resolve, GET /projN/ 200 렌더
- 각 projN/app.py 독립 실행도 정상, 전체 py_compile 통과
- proj2 데이터 추출 클릭 시 진행 페이지가 뜨고 완료 후 확인/저장 화면으로 전환,
  추출이 길어도 워커 타임아웃(500) 없이 처리

========================
추가 요구
========================
- Flask 초보자도 이해할 수 있게 설명, 기존 코드 최소 수정, 유지보수·확장(proj4/5) 용이
- 보안/타임아웃 등 중요한 부분은 "왜 그런지" 이유까지 설명
- 단순 예제가 아니라 실제 프로젝트에 바로 적용 가능한 형태로 작성