from flask import Blueprint, Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime
try:
    from .config import Config
    from .services.naver_api import get_naver_inlink_articles
    from .services.gemini_ai import analyze_issue_with_gemini, generate_summary_card
    from .services.naver_datalab import get_search_trend, get_age_trend, get_keyword_comparison
    from .services.rag import (
        add_document, search_and_format_for_prompt,
        get_all_documents, delete_document, get_doc_count,
    )
    from .services.task_store import (
        create_task, get_result as load_result, get_status as load_status,
        set_result, set_status, update_result,
    )
except ImportError:
    from config import Config
    from services.naver_api import get_naver_inlink_articles
    from services.gemini_ai import analyze_issue_with_gemini, generate_summary_card
    from services.naver_datalab import get_search_trend, get_age_trend, get_keyword_comparison
    from services.rag import (
        add_document, search_and_format_for_prompt,
        get_all_documents, delete_document, get_doc_count,
    )
    from services.task_store import (
        create_task, get_result as load_result, get_status as load_status,
        set_result, set_status, update_result,
    )
from werkzeug.utils import secure_filename
import markdown, threading, uuid, os, json
from collections import Counter

bp = Blueprint("proj3", __name__, template_folder="templates")

UPLOAD_FOLDER = str(Config.UPLOAD_DIR)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXT = {"txt", "pdf", "docx", "md"}


@bp.route('/', methods=['GET'])
def index():
    return render_template('proj3/index.html')


@bp.route('/analyze', methods=['POST'])
def analyze():
    keyword = (request.form.get('keyword') or '').strip()
    company_name = request.form.get('company_name', '포스코홀딩스')
    if not keyword:
        return redirect(url_for('proj3.index'))
    task_id = str(uuid.uuid4())[:8]
    create_task(task_id, keyword, company_name)
    threading.Thread(
        target=_run_analysis,
        args=(task_id, keyword, company_name),
        daemon=True,
    ).start()
    return render_template('proj3/progress.html', keyword=keyword, company_name=company_name, task_id=task_id)


def _extract_article_stats(parsed_articles):
    """기사 텍스트에서 날짜별 건수, 매체별 건수 추출"""
    date_counts = Counter()
    media_counts = Counter()

    lines = parsed_articles.split('\n')
    for line in lines:
        # 매체 추출
        if line.strip().startswith('- 매체:'):
            media = line.replace('- 매체:', '').strip()
            if media and media != '알 수 없음':
                media_counts[media] += 1
        # 날짜 추출 (pubDate에서 날짜만)
        if line.strip().startswith('- 일시:'):
            date_str = line.replace('- 일시:', '').strip()
            # "Wed, 16 Apr 2026 09:00:00 +0900" → "04.16"
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(date_str)
                date_key = dt.strftime('%m.%d')
                date_counts[date_key] += 1
            except:
                pass

    return dict(date_counts), dict(media_counts)


def _run_analysis(task_id, keyword, company_name):
    try:
        issue_query = f"{company_name} {keyword}".strip()
        set_status(task_id, 1, f"네이버 뉴스에서 '{company_name} AND {keyword}' 조건으로 기사 원문을 수집하고 있습니다...")
        parsed_articles = get_naver_inlink_articles(issue_query)
        if not parsed_articles:
            set_status(task_id, -1, f"'{company_name} AND {keyword}' 조건의 기사 수집 실패.")
            return

        article_count = parsed_articles.count('[기사')
        set_status(task_id, 2, f"{article_count}건 기사 파싱 완료")

        # 기사 통계 추출
        date_counts, media_counts = _extract_article_stats(parsed_articles)

        set_status(task_id, 3, "내부 자료(RAG) + 데이터랩 검색 중...")
        rag_text, rag_docs = search_and_format_for_prompt(issue_query, company=company_name, n_results=5)
        ct, cd = search_and_format_for_prompt(issue_query, company="포스코그룹 공통", n_results=3)
        if cd:
            rag_text += "\n\n" + ct
            rag_docs += cd

        # 데이터랩 (일별 트렌드 + 연령대 + 관련 키워드 비교)
        trend_data = get_search_trend(issue_query)
        age_data = get_age_trend(issue_query)

        # 관련 키워드 비교 (키워드에서 주요 단어 추출)
        sub_keywords = keyword.split() if len(keyword.split()) > 1 else [keyword]
        comparison_data = get_keyword_comparison(sub_keywords[:5]) if len(sub_keywords) > 1 else None

        # 중간 결과 저장
        set_result(task_id, {
            "keyword": keyword,
            "company_name": company_name,
            "issue_query": issue_query,
            "article_count": article_count,
            "rag_count": len(rag_docs),
            "analysis_date": datetime.now().strftime("%Y.%m.%d %H:%M"),
            "trend_json": json.dumps(trend_data) if trend_data else "null",
            "age_json": json.dumps(age_data) if age_data else "null",
            "comparison_json": json.dumps(comparison_data) if comparison_data else "null",
            "date_counts_json": json.dumps(date_counts) if date_counts else "null",
            "media_counts_json": json.dumps(media_counts) if media_counts else "null",
            "parsed_articles": parsed_articles,
            "report_html": "",
            "report_md": "",
            "summary": "",
            "ready": False,
        })

        set_status(task_id, 4, f"AI가 {company_name} 관점에서 분석 중...")
        report_md = analyze_issue_with_gemini(keyword, parsed_articles, rag_text, company_name, issue_query)

        set_status(task_id, 5, "리포트 구성 중...")
        report_html = markdown.markdown(report_md, extensions=['tables', 'fenced_code', 'nl2br'])

        set_status(task_id, 6, "경영진 3줄 요약 생성 중...")
        summary = generate_summary_card(report_md, keyword, company_name)

        update_result(task_id, {
            "report_html": report_html,
            "report_md": report_md,
            "summary": summary,
            "ready": True,
        })
        set_status(task_id, 7, "분석 완료!")
    except Exception as e:
        set_status(task_id, -1, f"오류: {str(e)}")
        data = load_result(task_id)
        if data:
            update_result(task_id, {
                "ready": True,
                "report_html": f"<p style='color:#ff6b6b'>오류: {str(e)}</p>",
            })


@bp.route('/status/<task_id>')
def get_status(task_id):
    return jsonify(load_status(task_id))

@bp.route('/result/<task_id>')
def get_result(task_id):
    data = load_result(task_id)
    if not data:
        return "분석 결과를 찾을 수 없습니다.", 404
    return render_template('proj3/result.html', task_id=task_id, **data)

@bp.route('/api/report/<task_id>')
def api_report(task_id):
    data = load_result(task_id)
    if not data:
        return jsonify({"ready": False, "msg": "대기 중..."})
    status = load_status(task_id)
    if data.get("ready"):
        return jsonify({"ready": True, "report_html": data["report_html"],
                        "report_md": data["report_md"], "summary": data["summary"]})
    return jsonify({"ready": False, "msg": status.get("msg", "분석 중..."), "step": status.get("step", 0)})


# ── RAG ──
@bp.route('/documents')
def documents():
    docs = get_all_documents()
    return render_template('proj3/documents.html', documents=docs, doc_count=len(docs),
        chunk_count=get_doc_count(), company_count=len(set(d["company"] for d in docs)),
        flash_msg=request.args.get('msg'), flash_type=request.args.get('type', 'success'))

@bp.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file or file.filename == '':
        return redirect(url_for('proj3.documents', msg='파일선택필요', type='error'))
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXT:
        return redirect(url_for('proj3.documents', msg='미지원형식', type='error'))
    fn = secure_filename(file.filename) or file.filename
    fp = os.path.join(UPLOAD_FOLDER, fn)
    file.save(fp)
    text = _read_file(fp, ext)
    if not text:
        return redirect(url_for('proj3.documents', msg='읽기실패', type='error'))
    _, cc = add_document(text, fn, request.form.get('category', '기타'), request.form.get('company', '포스코홀딩스'))
    return redirect(url_for('proj3.documents', msg=f'✅{fn}업로드({cc}청크)', type='success'))

@bp.route('/delete_doc', methods=['POST'])
def delete_doc():
    c = delete_document(request.form.get('doc_id'))
    return redirect(url_for('proj3.documents', msg=f'🗑️삭제({c}청크)', type='success'))

def _read_file(fp, ext):
    try:
        if ext in ('txt', 'md'):
            return open(fp, 'r', encoding='utf-8').read()
        elif ext == 'pdf':
            try:
                import fitz
                d = fitz.open(fp); t = "".join(p.get_text() for p in d); d.close(); return t
            except:
                return open(fp, 'rb').read().decode('utf-8', errors='ignore')
        elif ext == 'docx':
            from docx import Document
            return "\n".join(p.text for p in Document(fp).paragraphs)
    except: pass
    return ""


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.secret_key = app.config["SECRET_KEY"]
    app.register_blueprint(bp)
    return app


app = create_app()


if __name__ == '__main__':
    app.run(host=app.config["HOST"], port=app.config["PORT"], debug=app.config["DEBUG"])
