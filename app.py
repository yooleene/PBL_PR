import json
import os
import sqlite3
from collections import Counter

from dotenv import load_dotenv
from flask import Flask, flash, g, redirect, render_template, request, url_for

# .env 파일을 읽어서 OPENAI_API_KEY 같은 환경 변수를 사용할 수 있게 합니다.
load_dotenv()

try:
    # OpenAI 패키지가 설치되어 있지 않아도 앱이 실행되도록 예외 처리합니다.
    from openai import OpenAI
except ImportError:
    OpenAI = None


app = Flask(__name__)
app.config["SECRET_KEY"] = "simple-media-intelligence-secret"
app.config["DATABASE"] = os.path.join(os.path.dirname(__file__), "media_intelligence.db")


def get_database_connection():
    """
    Flask 요청 1회당 SQLite 연결을 1개만 만들어서 재사용합니다.
    """
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_database_connection(error):
    """
    요청이 끝나면 DB 연결을 닫아줍니다.
    """
    db = g.pop("db", None)
    if db is not None:
        db.close()


def create_tables_if_needed():
    """
    앱 시작 시 필요한 테이블을 만듭니다.
    """
    db = get_database_connection()

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS reporters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            media_company TEXT NOT NULL,
            beat TEXT NOT NULL,
            email TEXT,
            notes TEXT
        )
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            published_date TEXT NOT NULL,
            feedback_count INTEGER DEFAULT 0,
            FOREIGN KEY (reporter_id) REFERENCES reporters (id)
        )
        """
    )

    db.commit()


def seed_sample_data_if_empty():
    """
    DB가 비어 있을 때만 샘플 기자 3명과 기사 데이터를 넣습니다.
    """
    db = get_database_connection()
    reporter_count = db.execute("SELECT COUNT(*) AS count FROM reporters").fetchone()["count"]

    if reporter_count > 0:
        return

    sample_reporters = [
        {
            "name": "김민준",
            "media_company": "데일리포커스",
            "beat": "산업/기업",
            "email": "mkim@example.com",
            "notes": "기업 전략과 실적 이슈에 관심이 많음",
        },
        {
            "name": "이서연",
            "media_company": "정책투데이",
            "beat": "정책/사회",
            "email": "seoyeon@example.com",
            "notes": "사회적 영향과 정책 변화에 민감함",
        },
        {
            "name": "박지훈",
            "media_company": "비즈니스와치",
            "beat": "ESG/리스크",
            "email": "jpark@example.com",
            "notes": "위기관리와 안전 이슈를 자주 다룸",
        },
    ]

    reporter_ids = []
    for reporter in sample_reporters:
        cursor = db.execute(
            """
            INSERT INTO reporters (name, media_company, beat, email, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                reporter["name"],
                reporter["media_company"],
                reporter["beat"],
                reporter["email"],
                reporter["notes"],
            ),
        )
        reporter_ids.append(cursor.lastrowid)

    sample_articles = [
        (
            reporter_ids[0],
            "A기업, 신사업 확대에 속도",
            "A기업은 올해 신사업 투자 규모를 확대하며 성장 전략을 강화했다. 시장에서는 적극적인 투자 방향을 긍정적으로 보고 있다.",
            "2026-03-05",
            4,
        ),
        (
            reporter_ids[0],
            "A기업 실적 발표 후 시장 기대 커져",
            "A기업은 이번 분기 실적에서 예상보다 높은 매출을 기록했다. 투자자들은 향후 수익성 개선 가능성에도 주목하고 있다.",
            "2026-03-18",
            3,
        ),
        (
            reporter_ids[0],
            "A기업 공급망 이슈 점검 필요",
            "A기업은 공급망 운영에서 일부 부담을 안고 있다. 업계에서는 빠른 대응이 필요하다는 분석이 나온다.",
            "2026-04-01",
            5,
        ),
        (
            reporter_ids[1],
            "정부 정책 변화가 지역 산업에 미치는 영향",
            "새로운 정책 추진으로 지역 산업 구조가 바뀔 가능성이 커졌다. 현장에서는 기대와 우려가 함께 나오고 있다.",
            "2026-03-07",
            2,
        ),
        (
            reporter_ids[1],
            "공공지원 확대, 현장 체감은 아직 부족",
            "정부는 공공지원을 확대했지만 현장에서는 실질적 효과가 제한적이라는 평가가 나온다.",
            "2026-03-22",
            6,
        ),
        (
            reporter_ids[1],
            "정책 수혜 기업 증가, 후속 점검 필요",
            "정책 수혜를 받은 기업 수는 늘었지만 형평성과 지속성에 대한 점검 필요성이 제기된다.",
            "2026-04-02",
            4,
        ),
        (
            reporter_ids[2],
            "중대재해 대응 체계 강화 요구",
            "산업 현장에서 안전사고 우려가 이어지면서 기업의 대응 체계 강화가 요구되고 있다.",
            "2026-03-10",
            7,
        ),
        (
            reporter_ids[2],
            "ESG 공시 확대, 기업 준비 수준은 제각각",
            "ESG 공시 확대가 예고되면서 기업별 준비 수준 차이가 뚜렷하게 나타나고 있다.",
            "2026-03-25",
            5,
        ),
        (
            reporter_ids[2],
            "리스크 관리 미흡 기업에 시장 경고",
            "리스크 관리가 미흡한 기업들에 대해 시장의 경고 신호가 커지고 있다. 선제 대응이 중요하다는 지적이 나온다.",
            "2026-04-03",
            8,
        ),
    ]

    db.executemany(
        """
        INSERT INTO articles (reporter_id, title, content, published_date, feedback_count)
        VALUES (?, ?, ?, ?, ?)
        """,
        sample_articles,
    )

    db.commit()


def get_all_reporters():
    """
    기자 목록을 이름순으로 가져옵니다.
    """
    db = get_database_connection()
    return db.execute(
        """
        SELECT id, name, media_company, beat, email, notes
        FROM reporters
        ORDER BY name
        """
    ).fetchall()


def get_single_reporter(reporter_id):
    """
    기자 1명의 기본 정보를 가져옵니다.
    """
    db = get_database_connection()
    return db.execute(
        """
        SELECT id, name, media_company, beat, email, notes
        FROM reporters
        WHERE id = ?
        """,
        (reporter_id,),
    ).fetchone()


def get_articles_for_reporter(reporter_id, start_date=None, end_date=None):
    """
    기자의 기사 목록을 가져옵니다.
    날짜가 주어지면 해당 기간으로 필터링합니다.
    """
    db = get_database_connection()

    query = """
        SELECT id, reporter_id, title, content, published_date, feedback_count
        FROM articles
        WHERE reporter_id = ?
    """
    values = [reporter_id]

    if start_date:
        query += " AND published_date >= ?"
        values.append(start_date)

    if end_date:
        query += " AND published_date <= ?"
        values.append(end_date)

    query += " ORDER BY published_date DESC"

    return db.execute(query, values).fetchall()


def create_new_reporter(name, media_company, beat, email, notes):
    """
    폼에서 받은 값으로 기자를 등록합니다.
    """
    db = get_database_connection()
    db.execute(
        """
        INSERT INTO reporters (name, media_company, beat, email, notes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name, media_company, beat, email, notes),
    )
    db.commit()


def build_simple_summary(articles):
    """
    기사 제목을 이용해 매우 단순한 요약을 만듭니다.
    OpenAI 응답이 없을 때도 화면이 동작하도록 하는 기본 요약입니다.
    """
    if not articles:
        return "선택한 기간에 기사가 없습니다."

    titles = [article["title"] for article in articles]
    joined_titles = ", ".join(titles[:3])
    return f"선택한 기간에는 총 {len(articles)}건의 기사가 있었고, 주요 기사로는 {joined_titles} 등이 있습니다."


def detect_tone_from_text(article_texts):
    """
    아주 쉬운 규칙 기반 논조 분석입니다.
    긍정/부정 단어 개수를 비교해 결과를 만듭니다.
    """
    positive_words = ["확대", "강화", "성장", "긍정", "개선", "기대", "수혜", "증가"]
    negative_words = ["우려", "부담", "부족", "미흡", "경고", "위기", "사고", "점검 필요"]

    positive_score = 0
    negative_score = 0

    for text in article_texts:
        for word in positive_words:
            positive_score += text.count(word)
        for word in negative_words:
            negative_score += text.count(word)

    if positive_score > negative_score:
        return "긍정"
    if negative_score > positive_score:
        return "부정"
    return "중립"


def extract_main_topics(article_texts):
    """
    미리 정해둔 키워드를 기준으로 주요 주제를 뽑습니다.
    """
    topic_keywords = {
        "정책": ["정책", "정부", "공공지원"],
        "실적": ["실적", "매출", "수익성"],
        "투자": ["투자", "신사업", "성장"],
        "안전": ["안전", "사고", "중대재해"],
        "ESG": ["ESG", "공시"],
        "리스크": ["리스크", "공급망", "경고"],
    }

    topic_counter = Counter()

    for text in article_texts:
        for topic_name, keywords in topic_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    topic_counter[topic_name] += 1

    if not topic_counter:
        return ["일반 이슈"]

    return [topic for topic, count in topic_counter.most_common(3)]


def calculate_simple_influence(article_count, total_feedback_count):
    """
    영향도를 기사 수와 피드백 수의 합으로 단순 계산합니다.
    """
    raw_score = article_count * 10 + total_feedback_count * 2

    if raw_score >= 50:
        level = "높음"
    elif raw_score >= 25:
        level = "보통"
    else:
        level = "낮음"

    return {"score": raw_score, "level": level}


def create_response_guide(tone, topics, influence_level):
    """
    아주 단순한 규칙 기반 대응 가이드를 만듭니다.
    """
    if tone == "부정":
        base_guide = "사실관계 확인 자료와 개선 계획을 먼저 준비하는 것이 좋습니다."
    elif tone == "긍정":
        base_guide = "성과와 수치를 정리한 자료를 중심으로 소통하는 것이 좋습니다."
    else:
        base_guide = "중립적인 추가 설명 자료와 배경 정보를 준비하는 것이 좋습니다."

    topic_guide = f"주요 관심 주제는 {', '.join(topics)} 입니다."

    if influence_level == "높음":
        influence_guide = "영향도가 높은 기자이므로 빠른 응답과 명확한 메시지 정리가 필요합니다."
    elif influence_level == "보통":
        influence_guide = "중간 수준 영향력을 고려해 핵심 메시지를 간결하게 전달하면 좋습니다."
    else:
        influence_guide = "기본 브리핑 자료 중심으로 대응해도 충분합니다."

    return f"{base_guide} {topic_guide} {influence_guide}"


def analyze_articles_with_local_rules(reporter, articles):
    """
    OpenAI API를 쓰지 못하는 상황에서 사용할 기본 분석 함수입니다.
    """
    article_texts = [f"{article['title']} {article['content']}" for article in articles]
    total_feedback_count = sum(article["feedback_count"] for article in articles)
    tone = detect_tone_from_text(article_texts)
    topics = extract_main_topics(article_texts)
    influence = calculate_simple_influence(len(articles), total_feedback_count)

    return {
        "reporter_name": reporter["name"],
        "summary": build_simple_summary(articles),
        "tone": tone,
        "topics": topics,
        "article_count": len(articles),
        "feedback_count": total_feedback_count,
        "influence_score": influence["score"],
        "influence_level": influence["level"],
        "response_guide": create_response_guide(tone, topics, influence["level"]),
        "analysis_source": "로컬 샘플 분석",
    }


def try_analyze_articles_with_openai(reporter, articles):
    """
    OPENAI_API_KEY가 있을 때만 OpenAI로 분석을 시도합니다.
    실패하면 None을 반환하고 로컬 분석으로 넘어갑니다.
    """
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key or OpenAI is None or not articles:
        return None

    article_payload = [
        {
            "title": article["title"],
            "content": article["content"],
            "published_date": article["published_date"],
            "feedback_count": article["feedback_count"],
        }
        for article in articles
    ]

    prompt = f"""
당신은 기자 분석 보조 시스템입니다.
아래 기자와 기사 목록을 보고 JSON으로만 답변하세요.

기자 이름: {reporter["name"]}
출입 분야: {reporter["beat"]}
언론사: {reporter["media_company"]}

기사 데이터:
{json.dumps(article_payload, ensure_ascii=False, indent=2)}

반드시 아래 형식의 JSON만 출력하세요.
{{
  "summary": "기사 요약",
  "tone": "긍정 또는 부정 또는 중립",
  "topics": ["주제1", "주제2", "주제3"],
  "response_guide": "대응 가이드"
}}
""".strip()

    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
        )

        raw_text = response.output_text.strip()
        data = json.loads(raw_text)

        total_feedback_count = sum(article["feedback_count"] for article in articles)
        influence = calculate_simple_influence(len(articles), total_feedback_count)

        return {
            "reporter_name": reporter["name"],
            "summary": data.get("summary", ""),
            "tone": data.get("tone", "중립"),
            "topics": data.get("topics", []),
            "article_count": len(articles),
            "feedback_count": total_feedback_count,
            "influence_score": influence["score"],
            "influence_level": influence["level"],
            "response_guide": data.get("response_guide", ""),
            "analysis_source": "OpenAI API 분석",
        }
    except Exception:
        return None


def analyze_articles(reporter, articles):
    """
    먼저 OpenAI를 시도하고, 실패하면 로컬 규칙 분석으로 처리합니다.
    """
    openai_result = try_analyze_articles_with_openai(reporter, articles)
    if openai_result:
        return openai_result
    return analyze_articles_with_local_rules(reporter, articles)


@app.route("/")
def home():
    """
    메인 페이지입니다.
    """
    reporters = get_all_reporters()
    return render_template("home.html", reporters=reporters)


@app.route("/reporters")
def reporter_list():
    """
    기자 목록 페이지입니다.
    """
    reporters = get_all_reporters()
    return render_template("reporter_list.html", reporters=reporters)


@app.route("/reporters/new", methods=["GET", "POST"])
def reporter_create():
    """
    기자 등록 페이지입니다.
    """
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        media_company = request.form.get("media_company", "").strip()
        beat = request.form.get("beat", "").strip()
        email = request.form.get("email", "").strip()
        notes = request.form.get("notes", "").strip()

        if not name or not media_company or not beat:
            flash("이름, 언론사, 출입 분야는 꼭 입력해야 합니다.")
            return render_template("reporter_form.html")

        create_new_reporter(name, media_company, beat, email, notes)
        flash("기자가 등록되었습니다.")
        return redirect(url_for("reporter_list"))

    return render_template("reporter_form.html")


@app.route("/reporters/<int:reporter_id>", methods=["GET", "POST"])
def reporter_detail(reporter_id):
    """
    기자 상세 페이지입니다.
    GET 요청이면 기본 정보와 기사 목록을 보여주고,
    POST 요청이면 날짜 조건에 맞는 기사 분석 결과까지 보여줍니다.
    """
    reporter = get_single_reporter(reporter_id)

    if reporter is None:
        flash("기자를 찾을 수 없습니다.")
        return redirect(url_for("reporter_list"))

    analysis_result = None
    start_date = ""
    end_date = ""

    if request.method == "POST":
        start_date = request.form.get("start_date", "").strip()
        end_date = request.form.get("end_date", "").strip()

        filtered_articles = get_articles_for_reporter(reporter_id, start_date, end_date)

        if not filtered_articles:
            flash("선택한 기간에 해당하는 기사가 없습니다.")
        else:
            analysis_result = analyze_articles(reporter, filtered_articles)

    articles = get_articles_for_reporter(reporter_id)

    return render_template(
        "reporter_detail.html",
        reporter=reporter,
        articles=articles,
        analysis_result=analysis_result,
        start_date=start_date,
        end_date=end_date,
    )


@app.before_request
def prepare_database():
    """
    첫 요청 전에 테이블 생성과 샘플 데이터 입력을 보장합니다.
    """
    create_tables_if_needed()
    seed_sample_data_if_empty()


if __name__ == "__main__":
    app.run(debug=True, port=5001)
