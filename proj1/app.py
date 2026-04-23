"""
네이버 기자 분석 웹 애플리케이션
Flask + Playwright + OpenAI
"""

import os
import threading
import uuid
from datetime import datetime
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    session,
    redirect,
    url_for,
)
from dotenv import load_dotenv

load_dotenv()

from utils.crawler import NaverJournalistCrawler
from utils.analyzer import OpenAIAnalyzer

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "naver-journalist-analyzer-secret")
app.config["JSON_AS_ASCII"] = False

# 진행 중인 작업 저장소 (프로덕션에서는 Redis 사용 권장)
JOBS: dict = {}


# ------------------------------------------------------------------ #
#  헬퍼
# ------------------------------------------------------------------ #

def _make_job() -> str:
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "status": "pending",
        "progress": 0,
        "message": "작업 시작 중…",
        "result": None,
        "error": None,
        "created_at": datetime.now().isoformat(),
    }
    return job_id


def _run_analysis(job_id: str, media_name: str, journalist_name: str):
    """백그라운드 스레드에서 크롤링 + 분석 실행"""
    def progress(msg: str, pct: int):
        if job_id in JOBS:
            JOBS[job_id]["message"] = msg
            JOBS[job_id]["progress"] = pct

    try:
        JOBS[job_id]["status"] = "running"

        # 1. 크롤링
        crawler = NaverJournalistCrawler(progress_callback=progress)
        crawl_result = crawler.search_journalist(media_name, journalist_name)

        if "error" in crawl_result:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["error"] = crawl_result["error"]
            return

        # 2. AI 분석 (관심분야·논조·키워드 / 토킹포인트 2회 분리 호출)
        progress("AI 분석 중…", 91)
        analyzer = OpenAIAnalyzer()
        analysis_result = analyzer.analyze(
            journalist_name=journalist_name,
            media_name=media_name,
            articles=crawl_result.get("articles", []),
            posco_articles=crawl_result.get("posco_articles_raw", []),
        )

        # 3. 결과 병합
        final = {
            **crawl_result,
            **analysis_result,
            "media_name": media_name,
        }

        JOBS[job_id]["status"] = "done"
        JOBS[job_id]["progress"] = 100
        JOBS[job_id]["message"] = "분석 완료"
        JOBS[job_id]["result"] = final

    except Exception as e:
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["error"] = str(e)


# ------------------------------------------------------------------ #
#  라우팅
# ------------------------------------------------------------------ #

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search():
    media_name = request.form.get("media_name", "").strip()
    journalist_name = request.form.get("journalist_name", "").strip()

    if not media_name or not journalist_name:
        return render_template(
            "index.html",
            error="매체명과 기자명을 모두 입력해 주세요.",
        )

    job_id = _make_job()
    thread = threading.Thread(
        target=_run_analysis,
        args=(job_id, media_name, journalist_name),
        daemon=True,
    )
    thread.start()

    return redirect(url_for("progress_page", job_id=job_id))


@app.route("/progress/<job_id>")
def progress_page(job_id: str):
    if job_id not in JOBS:
        return redirect(url_for("index"))
    job = JOBS[job_id]
    return render_template(
        "progress.html",
        job_id=job_id,
        message=job["message"],
        progress=job["progress"],
    )


@app.route("/api/status/<job_id>")
def api_status(job_id: str):
    if job_id not in JOBS:
        return jsonify({"error": "작업을 찾을 수 없습니다."}), 404
    job = JOBS[job_id]
    return jsonify({
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
        "error": job.get("error"),
    })


@app.route("/result/<job_id>")
def result_page(job_id: str):
    if job_id not in JOBS:
        return redirect(url_for("index"))
    job = JOBS[job_id]
    if job["status"] != "done":
        return redirect(url_for("progress_page", job_id=job_id))
    return render_template("result.html", data=job["result"])


if __name__ == "__main__":
    flask_debug = os.getenv("FLASK_DEBUG", "true").lower() in {"1", "true", "yes", "on"}
    flask_host = os.getenv("FLASK_HOST", "0.0.0.0")
    flask_port = int(os.getenv("FLASK_PORT", "5001"))
    app.run(debug=flask_debug, host=flask_host, port=flask_port)
