from flask import Flask, render_template, request, jsonify, redirect
from dotenv import load_dotenv
from datetime import datetime
from services.naver_api import get_naver_inlink_articles
from services.gemini_ai import analyze_issue_with_gemini, generate_summary_card
from services.naver_datalab import get_search_trend, get_age_trend, get_keyword_comparison
from services.rag import (
    add_document, search_and_format_for_prompt,
    get_all_documents, delete_document, get_doc_count,
)
from werkzeug.utils import secure_filename
import markdown, threading, uuid, os, json, re
from collections import Counter

load_dotenv()
app = Flask(__name__)
app.secret_key = 'posco-module3-secret-key'

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "data", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXT = {"txt", "pdf", "docx", "md"}
analysis_status = {}
analysis_results = {}


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    keyword = (request.form.get('keyword') or '').strip()
    company_name = request.form.get('company_name', '포스코홀딩스')
    if not keyword:
        return redirect('/')
    task_id = str(uuid.uuid4())[:8]
    threading.Thread(target=_run_analysis, args=(task_id, keyword, company_name)).start()
    return render_template('progress.html', keyword=keyword, company_name=company_name, task_id=task_id)


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
        analysis_status[task_id] = {"step": 1, "msg": f"네이버 뉴스에서 '{company_name} AND {keyword}' 조건으로 기사 원문을 수집하고 있습니다..."}
        parsed_articles = get_naver_inlink_articles(issue_query)
        if not parsed_articles:
            analysis_status[task_id] = {"step": -1, "msg": f"'{company_name} AND {keyword}' 조건의 기사 수집 실패."}
            return

        article_count = parsed_articles.count('[기사')
        analysis_status[task_id] = {"step": 2, "msg": f"{article_count}건 기사 파싱 완료"}

        # 기사 통계 추출
        date_counts, media_counts = _extract_article_stats(parsed_articles)

        analysis_status[task_id] = {"step": 3, "msg": "내부 자료(RAG) + 데이터랩 검색 중..."}
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
        analysis_results[task_id] = {
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
        }

        analysis_status[task_id] = {"step": 4, "msg": f"AI가 {company_name} 관점에서 분석 중..."}
        report_md = analyze_issue_with_gemini(keyword, parsed_articles, rag_text, company_name, issue_query)

        analysis_status[task_id] = {"step": 5, "msg": "리포트 구성 중..."}
        report_html = markdown.markdown(report_md, extensions=['tables', 'fenced_code', 'nl2br'])

        analysis_status[task_id] = {"step": 6, "msg": "경영진 3줄 요약 생성 중..."}
        summary = generate_summary_card(report_md, keyword, company_name)

        analysis_results[task_id].update({
            "report_html": report_html,
            "report_md": report_md,
            "summary": summary,
            "ready": True,
        })
        analysis_status[task_id] = {"step": 7, "msg": "분석 완료!"}
    except Exception as e:
        analysis_status[task_id] = {"step": -1, "msg": f"오류: {str(e)}"}
        if task_id in analysis_results:
            analysis_results[task_id]["ready"] = True
            analysis_results[task_id]["report_html"] = f"<p style='color:#ff6b6b'>❌ 오류: {str(e)}</p>"


@app.route('/status/<task_id>')
def get_status(task_id):
    return jsonify(analysis_status.get(task_id, {"step": 0, "msg": "대기 중..."}))

@app.route('/result/<task_id>')
def get_result(task_id):
    data = analysis_results.get(task_id)
    if not data:
        return "분석 결과를 찾을 수 없습니다.", 404
    return render_template('result.html', task_id=task_id, **data)

@app.route('/api/report/<task_id>')
def api_report(task_id):
    data = analysis_results.get(task_id)
    if not data:
        return jsonify({"ready": False, "msg": "대기 중..."})
    status = analysis_status.get(task_id, {})
    if data.get("ready"):
        return jsonify({"ready": True, "report_html": data["report_html"],
                        "report_md": data["report_md"], "summary": data["summary"]})
    return jsonify({"ready": False, "msg": status.get("msg", "분석 중..."), "step": status.get("step", 0)})


# ── RAG ──
@app.route('/documents')
def documents():
    docs = get_all_documents()
    return render_template('documents.html', documents=docs, doc_count=len(docs),
        chunk_count=get_doc_count(), company_count=len(set(d["company"] for d in docs)),
        flash_msg=request.args.get('msg'), flash_type=request.args.get('type', 'success'))

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file or file.filename == '':
        return redirect('/documents?msg=파일선택필요&type=error')
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXT:
        return redirect('/documents?msg=미지원형식&type=error')
    fn = secure_filename(file.filename) or file.filename
    fp = os.path.join(UPLOAD_FOLDER, fn)
    file.save(fp)
    text = _read_file(fp, ext)
    if not text:
        return redirect('/documents?msg=읽기실패&type=error')
    _, cc = add_document(text, fn, request.form.get('category', '기타'), request.form.get('company', '포스코홀딩스'))
    return redirect(f'/documents?msg=✅{fn}업로드({cc}청크)&type=success')

@app.route('/delete_doc', methods=['POST'])
def delete_doc():
    c = delete_document(request.form.get('doc_id'))
    return redirect(f'/documents?msg=🗑️삭제({c}청크)&type=success')

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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
