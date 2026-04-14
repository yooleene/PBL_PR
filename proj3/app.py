from flask import Flask, render_template, request, jsonify, redirect
from dotenv import load_dotenv
from datetime import datetime
from services.naver_api import get_naver_inlink_articles
from services.gemini_ai import analyze_issue_with_gemini, generate_summary_card
from services.rag import (
    add_document, search_and_format_for_prompt,
    get_all_documents, delete_document, get_doc_count,
)
from werkzeug.utils import secure_filename
import markdown
import threading
import uuid
import os

load_dotenv()
app = Flask(__name__)
app.secret_key = 'posco-module3-secret-key'

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "data", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXT = {"txt", "pdf", "docx", "md"}

# 분석 상태 저장
analysis_status = {}
analysis_results = {}


# ──────────────────────────────────────────────
# 메인 페이지
# ──────────────────────────────────────────────

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


# ──────────────────────────────────────────────
# 이슈 분석 (프로그레스 + 백그라운드)
# ──────────────────────────────────────────────

@app.route('/analyze', methods=['POST'])
def analyze():
    keyword = request.form.get('keyword')
    company_name = request.form.get('company_name', '포스코홀딩스')

    task_id = str(uuid.uuid4())[:8]

    thread = threading.Thread(
        target=_run_analysis,
        args=(task_id, keyword, company_name)
    )
    thread.start()

    return render_template(
        'progress.html',
        keyword=keyword,
        company_name=company_name,
        task_id=task_id,
    )


def _run_analysis(task_id, keyword, company_name):
    """백그라운드 분석 실행"""
    try:
        # Step 1: 뉴스 크롤링
        analysis_status[task_id] = {"step": 1, "msg": "네이버 뉴스에서 기사 원문을 수집하고 있습니다..."}
        parsed_articles = get_naver_inlink_articles(keyword)

        if not parsed_articles:
            analysis_status[task_id] = {"step": -1, "msg": "기사 수집 실패. API 키를 확인해주세요."}
            return

        # Step 2: 기사 파싱 완료
        article_count = parsed_articles.count('[기사')
        analysis_status[task_id] = {"step": 2, "msg": f"{article_count}건의 기사 원문 파싱 완료"}

        # Step 3: RAG 검색
        analysis_status[task_id] = {"step": 3, "msg": "내부 자료(RAG)에서 관련 문서를 검색합니다..."}
        rag_text, rag_docs = search_and_format_for_prompt(keyword, company=company_name, n_results=5)
        # 그룹 공통 자료도 추가 검색
        common_text, common_docs = search_and_format_for_prompt(keyword, company="포스코그룹 공통", n_results=3)
        if common_docs:
            rag_text += "\n\n" + common_text
            rag_docs += common_docs

        # Step 4: Gemini 분석
        analysis_status[task_id] = {"step": 4, "msg": f"Gemini AI가 {company_name} 관점에서 종합 분석 중..."}
        report_md = analyze_issue_with_gemini(keyword, parsed_articles, rag_text, company_name)

        # Step 5: 리포트 생성
        analysis_status[task_id] = {"step": 5, "msg": "리포트를 구성하고 있습니다..."}
        report_html = markdown.markdown(report_md, extensions=['tables', 'fenced_code', 'nl2br'])

        # Step 6: 경영진 요약
        analysis_status[task_id] = {"step": 6, "msg": "경영진 공유용 3줄 요약을 생성합니다..."}
        summary = generate_summary_card(report_md, keyword, company_name)

        # 완료
        analysis_date = datetime.now().strftime("%Y.%m.%d %H:%M")

        analysis_results[task_id] = {
            "keyword": keyword,
            "company_name": company_name,
            "report_html": report_html,
            "report_md": report_md,
            "summary": summary,
            "article_count": article_count,
            "rag_count": len(rag_docs),
            "analysis_date": analysis_date,
        }
        analysis_status[task_id] = {"step": 7, "msg": "분석 완료!"}

    except Exception as e:
        analysis_status[task_id] = {"step": -1, "msg": f"오류 발생: {str(e)}"}


@app.route('/status/<task_id>')
def get_status(task_id):
    status = analysis_status.get(task_id, {"step": 0, "msg": "대기 중..."})
    return jsonify(status)


@app.route('/result/<task_id>')
def get_result(task_id):
    data = analysis_results.get(task_id)
    if not data:
        return "분석 결과를 찾을 수 없습니다.", 404
    analysis_status.pop(task_id, None)
    analysis_results.pop(task_id, None)
    return render_template('result.html', **data)


# ──────────────────────────────────────────────
# 문서 관리 (RAG)
# ──────────────────────────────────────────────

@app.route('/documents')
def documents():
    docs = get_all_documents()
    chunk_count = get_doc_count()
    companies = set(d["company"] for d in docs)
    return render_template(
        'documents.html',
        documents=docs,
        doc_count=len(docs),
        chunk_count=chunk_count,
        company_count=len(companies),
        flash_msg=request.args.get('msg'),
        flash_type=request.args.get('type', 'success'),
    )


@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file or file.filename == '':
        return redirect('/documents?msg=파일을 선택해주세요.&type=error')

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXT:
        return redirect('/documents?msg=지원하지 않는 파일 형식입니다.&type=error')

    filename = secure_filename(file.filename)
    # 한글 파일명 보존
    if not filename or filename == '':
        filename = file.filename
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    # 파일 읽기
    text = _read_file(filepath, ext)
    if not text:
        return redirect('/documents?msg=파일 내용을 읽을 수 없습니다.&type=error')

    company = request.form.get('company', '포스코홀딩스')
    category = request.form.get('category', '기타')

    # RAG 저장
    doc_id, chunk_count = add_document(text, filename, category, company)
    msg = f"✅ '{filename}' 업로드 완료! ({chunk_count}개 청크로 벡터DB 저장)"
    return redirect(f'/documents?msg={msg}&type=success')


@app.route('/delete_doc', methods=['POST'])
def delete_doc():
    doc_id = request.form.get('doc_id')
    count = delete_document(doc_id)
    msg = f"🗑️ 문서 삭제 완료 ({count}개 청크 제거)"
    return redirect(f'/documents?msg={msg}&type=success')


# ──────────────────────────────────────────────
# 파일 읽기 헬퍼
# ──────────────────────────────────────────────

def _read_file(filepath, ext):
    try:
        if ext in ('txt', 'md'):
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        elif ext == 'pdf':
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(filepath)
                text = ""
                for page in doc:
                    text += page.get_text()
                doc.close()
                return text
            except ImportError:
                with open(filepath, 'rb') as f:
                    return f.read().decode('utf-8', errors='ignore')
        elif ext == 'docx':
            try:
                from docx import Document
                doc = Document(filepath)
                return "\n".join(p.text for p in doc.paragraphs)
            except ImportError:
                return ""
    except Exception as e:
        print(f"[파일 읽기 오류] {e}")
    return ""


if __name__ == '__main__':
    app.run(debug=True, port=5000)
