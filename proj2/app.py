from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import re
import sqlite3
import ssl
import ast
import threading
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from flask import Blueprint, Flask, Response, flash, redirect, render_template, request, url_for


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)
DATABASE = INSTANCE_DIR / "safety_labor.db"

bp = Blueprint("proj2", __name__, template_folder="templates", static_folder="static")


class OpenAIQuotaError(RuntimeError):
    pass


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS speeches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                speech_date TEXT,
                actor TEXT,
                organization TEXT,
                venue TEXT,
                quote TEXT,
                keywords TEXT,
                source_title TEXT,
                source_url TEXT,
                source_name TEXT,
                raw_payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT,
                accident_date TEXT,
                accident_summary TEXT,
                external_response TEXT,
                implication TEXT,
                apology_text TEXT,
                source_title TEXT,
                source_url TEXT,
                source_name TEXT,
                raw_payload TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS analysis_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS company_accidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_description TEXT NOT NULL,
                apology_text TEXT,
                response_direction TEXT,
                context_snapshot TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS collection_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_on TEXT NOT NULL,
                ended_on TEXT NOT NULL,
                prompt_type TEXT NOT NULL,
                item_count INTEGER NOT NULL DEFAULT 0,
                skipped_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                error_message TEXT,
                raw_response TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_speeches_date ON speeches(speech_date DESC);
            CREATE INDEX IF NOT EXISTS idx_incidents_date ON incidents(accident_date DESC);
            CREATE INDEX IF NOT EXISTS idx_speeches_source_url ON speeches(source_url);
            CREATE INDEX IF NOT EXISTS idx_incidents_source_url ON incidents(source_url);
            """
        )


@bp.before_request
def ensure_schema() -> None:
    init_db()


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with get_db() as db:
        return db.execute(query, params).fetchall()


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    with get_db() as db:
        return db.execute(query, params).fetchone()


def parse_date(value: str, label: str) -> str:
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{label} 날짜 형식이 올바르지 않습니다.") from exc


def split_keywords(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def item_get(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None:
            return split_keywords(value)
    return ""


def extract_json_array(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()

    candidates = [text]
    array_match = re.search(r"\[[\s\S]*\]", text)
    if array_match:
        candidates.append(array_match.group(0))
    object_match = re.search(r"\{[\s\S]*\}", text)
    if object_match:
        candidates.append(object_match.group(0))

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("items", "speeches", "incidents", "data", "results"):
                if isinstance(payload.get(key), list):
                    return [item for item in payload[key] if isinstance(item, dict)]
            return [payload]
    raise ValueError("Gemini 응답에서 JSON 배열을 찾지 못했습니다.")


def parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()

    candidates = [text]
    object_match = re.search(r"\{[\s\S]*\}", text)
    if object_match:
        candidates.append(object_match.group(0))

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError(f"JSON 객체 파싱 실패: {text[:500]}")


def extract_grounding_sources(response: Any) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return sources
    metadata = getattr(candidates[0], "grounding_metadata", None)
    chunks = getattr(metadata, "grounding_chunks", None) or []
    for chunk in chunks:
        web = getattr(chunk, "web", None)
        if not web:
            continue
        title = str(getattr(web, "title", "") or "").strip()
        uri = str(getattr(web, "uri", "") or "").strip()
        if uri and not any(source["url"] == uri for source in sources):
            sources.append({"title": title, "url": uri})
    return sources


def build_source_suffix(sources: list[dict[str, str]]) -> str:
    if not sources:
        return ""
    lines = ["", "검색 grounding 출처:"]
    for source in sources[:12]:
        label = source["title"] or source["url"]
        lines.append(f"- {label}: {source['url']}")
    return "\n".join(lines)


def is_grounding_redirect_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    return parsed.netloc == "vertexaisearch.cloud.google.com" and "/grounding-api-redirect/" in parsed.path


def is_valid_article_url(url: str) -> bool:
    url = str(url or "").strip()
    return bool(url) and not is_grounding_redirect_url(url)


def resolve_redirect_url(url: str) -> str:
    url = clean_url(url)
    if not is_grounding_redirect_url(url):
        return url
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=8, context=ssl._create_unverified_context()) as response:
            final_url = clean_url(getattr(response, "url", "") or "")
    except (HTTPError, URLError, TimeoutError, ValueError):
        return url
    if final_url and final_url != url and not is_grounding_redirect_url(final_url):
        return final_url
    return url


def lookup_exact_article_source(title: str, source_name: str = "", published_date: str = "") -> dict[str, str]:
    title = str(title or "").strip()
    if not title:
        return {}
    prompt = f"""
다음 기사 제목에 해당하는 원문 기사 URL을 Google 검색 grounding으로 찾아주세요.
반드시 JSON 객체만 출력하세요. 마크다운이나 설명은 넣지 마세요.

검색 대상:
- 기사 제목: {title}
- 매체명: {source_name or "불명"}
- 보도일 또는 관련일: {published_date or "불명"}

출력 필드:
- source_title: 검색 결과의 정확한 기사 제목
- source_url: 언론사 또는 플랫폼의 실제 원문 URL. vertexaisearch.cloud.google.com/grounding-api-redirect URL은 절대 쓰지 마세요.
- source_name: 매체명
""".strip()
    try:
        text, sources = call_gemini_grounded(prompt)
        payload = parse_json_object(text)
    except Exception:
        return {}

    source_url = resolve_redirect_url(str(payload.get("source_url") or payload.get("url") or ""))
    if is_grounding_redirect_url(source_url):
        source_url = ""
    source_title = str(payload.get("source_title") or payload.get("title") or title).strip()
    source_name = str(payload.get("source_name") or payload.get("media") or source_name).strip()

    if not source_url:
        for source in sources:
            candidate_url = resolve_redirect_url(str(source.get("url") or ""))
            if candidate_url and not is_grounding_redirect_url(candidate_url):
                source_url = candidate_url
                source_title = str(source.get("title") or source_title).strip()
                break
    if not source_url:
        return {}
    return {
        "source_title": source_title or title,
        "source_url": source_url,
        "source_name": source_name,
    }


def normalized_primary_source(item: dict[str, Any], sources: list[dict[str, str]], date_value: str = "") -> dict[str, str]:
    source_title = item_get(item, "source_title", "title", "기사제목")
    source_url = item_get(item, "source_url", "url", "출처URL")
    source_name = item_get(item, "source_name", "media", "언론사", "플랫폼")
    if not source_title and sources:
        source_title = str(sources[0].get("title") or "").strip()
    if not source_url and sources:
        source_url = str(sources[0].get("url") or "").strip()
    source_url = resolve_redirect_url(source_url)
    if is_grounding_redirect_url(source_url):
        exact_source = lookup_exact_article_source(source_title, source_name, date_value)
        if exact_source:
            source_title = exact_source["source_title"] or source_title
            source_url = exact_source["source_url"] or source_url
            source_name = exact_source["source_name"] or source_name
    if source_title:
        item["source_title"] = source_title
    if source_url:
        item["source_url"] = source_url
    if source_name:
        item["source_name"] = source_name
    return {
        "source_title": source_title,
        "source_url": source_url,
        "source_name": source_name,
    }


def gemini_timeout_ms() -> int:
    # gunicorn --timeout(기본 180s)보다 짧게 잡아야 워커 강제종료(500) 대신
    # 정상 예외로 처리되어 사용자에게 안내 메시지가 나간다.
    try:
        seconds = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "150"))
    except ValueError:
        seconds = 150.0
    return max(1000, int(seconds * 1000))


def call_gemini_grounded(prompt: str) -> tuple[str, list[dict[str, str]]]:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(".env에 GOOGLE_API_KEY가 없습니다.")

    from google import genai
    from google.genai import types

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=gemini_timeout_ms()))
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(tools=[grounding_tool])
    response = client.models.generate_content(model=model, contents=prompt, config=config)
    text = getattr(response, "text", "") or ""
    return text, extract_grounding_sources(response)


def call_gemini_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(".env에 GOOGLE_API_KEY가 없어 Gemini fallback을 사용할 수 없습니다.")

    from google import genai
    from google.genai import types

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=gemini_timeout_ms()))
    response = client.models.generate_content(
        model=model,
        contents=f"{system_prompt}\n\n{user_prompt}",
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.25),
    )
    return parse_json_object(getattr(response, "text", "") or "{}")


def collect_speech_prompt(started_on: str, ended_on: str) -> str:
    period = f"{started_on}부터 {ended_on}까지"
    return f"""
프롬프트1 원문:
"이재명 대통령과, 김영훈 노동부장관이 안전 노동과 관련해 해당 기간에 발언한 내용을 언론이나 소셜미디어(유튜브, X, 페이스북 등)에 나온 내용을 모두 알려주고 출처도 명확히 알려줘"

해당 기간: {period}

위 요청을 Google 검색 grounding 기반으로 수행해 주세요.
반드시 JSON 배열만 출력하세요. 설명 문장, 마크다운, 코드블록은 넣지 마세요.
1개의 기사 또는 소셜미디어 게시물에 나온 1개의 발언 묶음을 1개 객체로 만드세요.
중복 기사, 단순 재인용, 안전/노동과 무관한 정치 일반 발언은 제외하세요.

각 객체 필드:
- speech_date: YYYY-MM-DD 형식. 불명확하면 보도일.
- actor: 발언자 이름.
- organization: 대상 인물의 기관/직책.
- venue: 발언 장소 또는 매체.
- quote: 주요 발언 내용 요약. 직접 인용이 있으면 짧게 포함.
- keywords: 핵심 키워드 배열.
- source_title: 기사 또는 게시물 제목.
- source_url: 출처 URL.
- source_name: 언론사/플랫폼명.
""".strip()


def collect_incident_prompt(started_on: str, ended_on: str) -> str:
    period = f"{started_on}부터 {ended_on}까지"
    return f"""
프롬프트2 원문:
"해당 기간에 일어난 중대재해 사고 관련해서도 모두 찾아줘."

해당 기간: {period}

위 요청을 Google 검색 grounding 기반으로 수행해 주세요.
반드시 JSON 배열만 출력하세요. 설명 문장, 마크다운, 코드블록은 넣지 마세요.
1개의 중대재해 사고를 1개 객체로 만드세요.
각 사고마다 대표 기사, 사고 개요, 회사·정부·노동부·수사기관의 대외대응을 함께 찾아 반영하세요.

각 객체 필드:
- company_name: 회사명 또는 사업장명.
- accident_date: YYYY-MM-DD 형식. 불명확하면 보도일.
- accident_summary: 사고내용.
- external_response: 회사/정부/노동부/수사기관의 대외대응.
- implication: 안전·노동 정책상 시사점.
- source_title: 대표 기사 제목.
- source_url: 대표 출처 URL.
- source_name: 대표 언론사/플랫폼명.
""".strip()


def source_exists(table: str, source_url: str) -> bool:
    if not source_url:
        return False
    row = fetch_one(f"SELECT id FROM {table} WHERE source_url = ? LIMIT 1", (source_url,))
    return row is not None


def duplicate_speech_id(source_url: str, speech_date: str, actor: str, quote: str) -> int | None:
    if source_url:
        row = fetch_one("SELECT id FROM speeches WHERE source_url = ? LIMIT 1", (source_url,))
    else:
        row = fetch_one(
            """
            SELECT id FROM speeches
            WHERE COALESCE(speech_date, '') = ?
              AND COALESCE(actor, '') = ?
              AND COALESCE(quote, '') = ?
            LIMIT 1
            """,
            (speech_date, actor, quote),
        )
    return int(row["id"]) if row else None


def duplicate_incident_id(source_url: str, company_name: str, accident_date: str, accident_summary: str) -> int | None:
    if source_url:
        row = fetch_one("SELECT id FROM incidents WHERE source_url = ? LIMIT 1", (source_url,))
    else:
        row = fetch_one(
            """
            SELECT id FROM incidents
            WHERE COALESCE(company_name, '') = ?
              AND COALESCE(accident_date, '') = ?
              AND COALESCE(accident_summary, '') = ?
            LIMIT 1
            """,
            (company_name, accident_date, accident_summary),
        )
    return int(row["id"]) if row else None


def insert_speech(item: dict[str, Any], sources: list[dict[str, str]]) -> bool:
    source = normalized_primary_source(item, sources, item_get(item, "speech_date", "date", "날짜"))
    source_url = source["source_url"]
    source_title = source["source_title"]
    speech_date = item_get(item, "speech_date", "date", "날짜")
    actor = item_get(item, "actor", "speaker", "발언자")
    organization = item_get(item, "organization", "position", "기관", "직책")
    venue = item_get(item, "venue", "place", "발언장소", "매체")
    quote = item_get(item, "quote", "content", "summary", "주요발언내용")
    keywords = item_get(item, "keywords", "핵심키워드")
    if duplicate_speech_id(source_url, speech_date, actor, quote):
        return False
    raw_payload = {"item": item, "grounding_sources": sources}
    timestamp = now_iso()
    with get_db() as db:
        db.execute(
            """
            INSERT INTO speeches (
                speech_date, actor, organization, venue, quote, keywords,
                source_title, source_url, source_name, raw_payload, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                speech_date,
                actor,
                organization,
                venue,
                quote,
                keywords,
                source_title,
                source_url,
                source["source_name"],
                json.dumps(raw_payload, ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
    return True


def insert_incident(item: dict[str, Any], sources: list[dict[str, str]]) -> bool:
    source = normalized_primary_source(item, sources, item_get(item, "accident_date", "date", "사고일"))
    source_url = source["source_url"]
    source_title = source["source_title"]
    for key in list(item):
        if "reaction" in key.lower() or "반응" in key:
            item.pop(key, None)
    company_name = item_get(item, "company_name", "company", "회사명")
    accident_date = item_get(item, "accident_date", "date", "사고일")
    accident_summary = item_get(item, "accident_summary", "summary", "accident_content", "사고내용")
    external_response = item_get(item, "external_response", "response", "대외대응")
    implication = item_get(item, "implication", "insight", "시사점")
    apology_text = item_get(item, "apology_text", "사과문")
    if duplicate_incident_id(source_url, company_name, accident_date, accident_summary):
        return False
    raw_payload = {"item": item, "grounding_sources": sources}
    timestamp = now_iso()
    with get_db() as db:
        db.execute(
            """
            INSERT INTO incidents (
                company_name, accident_date, accident_summary, external_response,
                implication, apology_text, source_title, source_url, source_name,
                raw_payload, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_name,
                accident_date,
                accident_summary,
                external_response,
                implication,
                apology_text,
                source_title,
                source_url,
                source["source_name"],
                json.dumps(raw_payload, ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
    return True


def upsert_speech_from_csv(item: dict[str, Any]) -> str:
    source = normalized_primary_source(item, [], item_get(item, "speech_date", "date", "날짜"))
    source_url = source["source_url"]
    source_title = source["source_title"]
    speech_date = item_get(item, "speech_date", "date", "날짜")
    actor = item_get(item, "actor", "speaker", "발언자")
    organization = item_get(item, "organization", "position", "기관", "직책")
    venue = item_get(item, "venue", "place", "발언장소", "매체")
    quote = item_get(item, "quote", "content", "summary", "주요발언내용")
    keywords = item_get(item, "keywords", "핵심키워드")
    duplicate_id = duplicate_speech_id(source_url, speech_date, actor, quote)
    if not duplicate_id:
        return "inserted" if insert_speech(item, []) else "skipped"

    raw_payload = {"item": item, "csv_upload": True}
    with get_db() as db:
        db.execute(
            """
            UPDATE speeches
            SET speech_date = ?, actor = ?, organization = ?, venue = ?,
                quote = ?, keywords = ?, source_title = ?, source_url = ?,
                source_name = ?, raw_payload = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                speech_date,
                actor,
                organization,
                venue,
                quote,
                keywords,
                source_title,
                source_url,
                source["source_name"],
                json.dumps(raw_payload, ensure_ascii=False),
                now_iso(),
                duplicate_id,
            ),
        )
    return "updated"


def upsert_incident_from_csv(item: dict[str, Any]) -> str:
    for key in list(item):
        if "reaction" in key.lower() or "반응" in key:
            item.pop(key, None)
    source = normalized_primary_source(item, [], item_get(item, "accident_date", "date", "사고일"))
    source_url = source["source_url"]
    source_title = source["source_title"]
    company_name = item_get(item, "company_name", "company", "회사명")
    accident_date = item_get(item, "accident_date", "date", "사고일")
    accident_summary = item_get(item, "accident_summary", "summary", "accident_content", "사고내용")
    external_response = item_get(item, "external_response", "response", "대외대응")
    implication = item_get(item, "implication", "insight", "시사점")
    apology_text = item_get(item, "apology_text", "사과문")
    duplicate_id = duplicate_incident_id(source_url, company_name, accident_date, accident_summary)
    if not duplicate_id:
        return "inserted" if insert_incident(item, []) else "skipped"

    raw_payload = {"item": item, "csv_upload": True}
    with get_db() as db:
        db.execute(
            """
            UPDATE incidents
            SET company_name = ?, accident_date = ?, accident_summary = ?,
                external_response = ?, implication = ?, apology_text = ?,
                source_title = ?, source_url = ?, source_name = ?,
                raw_payload = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                company_name,
                accident_date,
                accident_summary,
                external_response,
                implication,
                apology_text,
                source_title,
                source_url,
                source["source_name"],
                json.dumps(raw_payload, ensure_ascii=False),
                now_iso(),
                duplicate_id,
            ),
        )
    return "updated"


SPEECH_CSV_MAPPING = {
    "speech_date": ("speech_date", "date", "날짜"),
    "actor": ("actor", "speaker", "대상인물", "발언자"),
    "organization": ("organization", "position", "기관", "직책"),
    "venue": ("venue", "place", "발언장소", "매체"),
    "quote": ("quote", "content", "summary", "주요발언내용", "발언내용", "요약"),
    "keywords": ("keywords", "핵심키워드", "키워드"),
    "source_title": ("source_title", "title", "주요발언기사출처", "기사출처", "대표출처", "제목"),
    "source_url": ("source_url", "url", "출처URL", "URL", "링크"),
    "source_name": ("source_name", "media", "출처명", "언론사", "플랫폼"),
}

INCIDENT_CSV_MAPPING = {
    "company_name": ("company_name", "company", "회사명", "사업장명"),
    "accident_date": ("accident_date", "date", "사고일", "날짜"),
    "accident_summary": ("accident_summary", "summary", "accident_content", "사고내용", "사고개요", "요약"),
    "external_response": ("external_response", "response", "대외대응", "대응"),
    "implication": ("implication", "insight", "시사점"),
    "apology_text": ("apology_text", "사과문"),
    "source_title": ("source_title", "title", "대표출처", "기사출처", "제목"),
    "source_url": ("source_url", "url", "출처URL", "URL", "링크"),
    "source_name": ("source_name", "media", "출처명", "언론사", "플랫폼"),
}


def normalize_csv_header(value: str) -> str:
    return re.sub(r"[\s_·./()\\-]+", "", str(value or "").strip().lstrip("\ufeff").lower())


def decode_uploaded_csv(file_storage: Any) -> str:
    payload = file_storage.read()
    if not payload:
        raise ValueError("CSV 파일이 비어 있습니다.")
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV 인코딩을 읽을 수 없습니다. UTF-8 또는 CP949 CSV로 저장해 주세요.")


def uploaded_csv_rows(file_storage: Any) -> list[dict[str, str]]:
    text = decode_uploaded_csv(file_storage)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV 헤더가 없습니다.")
    return [dict(row) for row in reader]


def csv_cell(row: dict[str, str], aliases: tuple[str, ...]) -> str:
    normalized_row = {normalize_csv_header(key): str(value or "").strip() for key, value in row.items() if key}
    for alias in aliases:
        value = normalized_row.get(normalize_csv_header(alias))
        if value:
            return value
    return ""


def csv_item(row: dict[str, str], mapping: dict[str, tuple[str, ...]]) -> dict[str, str]:
    return {field: csv_cell(row, aliases) for field, aliases in mapping.items()}


def import_csv_items(
    file_storage: Any,
    mapping: dict[str, tuple[str, ...]],
    upserter: Any,
) -> tuple[int, int, int, int]:
    inserted = 0
    updated = 0
    skipped = 0
    empty = 0
    for row in uploaded_csv_rows(file_storage):
        item = csv_item(row, mapping)
        if not any(item.values()):
            empty += 1
            continue
        result = upserter(item)
        if result == "inserted":
            inserted += 1
        elif result == "updated":
            updated += 1
        else:
            skipped += 1
    return inserted, updated, skipped, empty


def record_collection_run(
    started_on: str,
    ended_on: str,
    prompt_type: str,
    item_count: int,
    skipped_count: int,
    status: str,
    raw_response: str = "",
    error_message: str = "",
) -> None:
    with get_db() as db:
        db.execute(
            """
            INSERT INTO collection_runs (
                started_on, ended_on, prompt_type, item_count, skipped_count,
                status, error_message, raw_response, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                started_on,
                ended_on,
                prompt_type,
                item_count,
                skipped_count,
                status,
                error_message,
                raw_response,
                now_iso(),
            ),
        )


def run_collection(started_on: str, ended_on: str) -> dict[str, tuple[int, int]]:
    payload = extract_collection(started_on, ended_on)
    return save_collection_payload(payload)


def collection_job(key: str, started_on: str, ended_on: str) -> tuple[str, str]:
    jobs = {
        "speeches": ("주요인사발언", collect_speech_prompt(started_on, ended_on)),
        "incidents": ("중대재해사례", collect_incident_prompt(started_on, ended_on)),
    }
    if key not in jobs:
        raise ValueError("지원하지 않는 데이터 구분입니다.")
    return jobs[key]


def extract_collection_section(key: str, started_on: str, ended_on: str) -> dict[str, Any]:
    label, prompt = collection_job(key, started_on, ended_on)
    raw_response = ""
    try:
        raw_response, sources = call_gemini_grounded(prompt)
        items = extract_json_array(raw_response)
    except Exception as exc:
        record_collection_run(started_on, ended_on, label, 0, 0, "failed", raw_response, str(exc))
        raise RuntimeError(f"{label} 추출 실패: {exc}") from exc
    return {
        "started_on": started_on,
        "ended_on": ended_on,
        "sections": {
            key: {
                "label": label,
                "items": items,
                "sources": sources,
                "raw_response": raw_response,
            }
        },
    }


def extract_collection(started_on: str, ended_on: str) -> dict[str, Any]:
    sections: dict[str, dict[str, Any]] = {}
    for key in ("speeches", "incidents"):
        payload = extract_collection_section(key, started_on, ended_on)
        sections.update(payload["sections"])
    return {
        "started_on": started_on,
        "ended_on": ended_on,
        "sections": sections,
    }


def save_collection_payload(payload: dict[str, Any]) -> dict[str, tuple[int, int]]:
    results: dict[str, tuple[int, int]] = {}
    started_on = str(payload.get("started_on", ""))
    ended_on = str(payload.get("ended_on", ""))
    sections = payload.get("sections") if isinstance(payload.get("sections"), dict) else {}
    jobs = {
        "speeches": ("주요인사발언", insert_speech),
        "incidents": ("중대재해사례", insert_incident),
    }
    for key, (label, inserter) in jobs.items():
        if key not in sections:
            continue
        section = sections.get(key) if isinstance(sections.get(key), dict) else {}
        items = section.get("items") if isinstance(section.get("items"), list) else []
        sources = section.get("sources") if isinstance(section.get("sources"), list) else []
        raw_response = str(section.get("raw_response", ""))
        inserted = 0
        skipped = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            if inserter(item, sources):
                inserted += 1
            else:
                skipped += 1
        record_collection_run(started_on, ended_on, label, inserted, skipped, "saved", raw_response)
        results[label] = (inserted, skipped)
    return results


def rows_as_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def context_for_ai(limit: int = 80) -> dict[str, Any]:
    speeches = rows_as_dicts(
        fetch_all(
            """
            SELECT speech_date, actor, organization, venue, quote, keywords,
                   source_title, source_url
            FROM speeches
            ORDER BY COALESCE(speech_date, '') DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
    )
    incidents = rows_as_dicts(
        fetch_all(
            """
            SELECT company_name, accident_date, accident_summary, external_response,
                   implication, apology_text, source_title, source_url
            FROM incidents
            ORDER BY COALESCE(accident_date, '') DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
    )
    company_accidents = rows_as_dicts(
        fetch_all(
            """
            SELECT incident_description, apology_text, response_direction, created_at
            FROM company_accidents
            ORDER BY id DESC
            LIMIT 30
            """
        )
    )
    return {
        "speeches": speeches,
        "incidents": incidents,
        "company_accidents": company_accidents,
    }


def table_count(table: str) -> int:
    row = fetch_one(f"SELECT COUNT(*) AS count FROM {table}")
    return int(row["count"]) if row else 0


def database_search_context(limit: int = 160) -> dict[str, Any]:
    speeches = rows_as_dicts(
        fetch_all(
            """
            SELECT id, speech_date, actor, organization, venue, quote, keywords,
                   source_title, source_url, source_name
            FROM speeches
            ORDER BY COALESCE(speech_date, '') DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
    )
    incidents = rows_as_dicts(
        fetch_all(
            """
            SELECT id, company_name, accident_date, accident_summary, external_response,
                   implication, apology_text, source_title, source_url, source_name
            FROM incidents
            ORDER BY COALESCE(accident_date, '') DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        )
    )
    company_accidents = rows_as_dicts(
        fetch_all(
            """
            SELECT id, incident_description, apology_text, response_direction, created_at
            FROM company_accidents
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
    )
    collection_runs = rows_as_dicts(
        fetch_all(
            """
            SELECT id, started_on, ended_on, prompt_type, item_count, skipped_count,
                   status, error_message, created_at
            FROM collection_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
    )
    analysis_reports = []
    for row in fetch_all(
        """
        SELECT id, body, created_at
        FROM analysis_reports
        ORDER BY id DESC
        LIMIT 20
        """
    ):
        body = str(row["body"] or "")
        try:
            parsed_body = json.loads(body)
        except json.JSONDecodeError:
            parsed_body = body
        analysis_reports.append(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "body": parsed_body,
            }
        )
    return {
        "counts": {
            "speeches": table_count("speeches"),
            "incidents": table_count("incidents"),
            "company_accidents": table_count("company_accidents"),
            "analysis_reports": table_count("analysis_reports"),
            "collection_runs": table_count("collection_runs"),
        },
        "speeches": speeches,
        "incidents": incidents,
        "company_accidents": company_accidents,
        "collection_runs": collection_runs,
        "analysis_reports": analysis_reports,
    }


def search_terms(query: str) -> list[str]:
    terms = re.findall(r"[0-9A-Za-z가-힣]{2,}", query.lower())
    terms.extend(date_search_terms(query))
    return list(dict.fromkeys(terms))


def date_search_terms(query: str) -> list[str]:
    terms: list[str] = []
    for match in re.finditer(r"(?:(20\d{2})\s*년\s*)?(1[0-2]|0?[1-9])\s*월\s*(3[01]|[12]\d|0?[1-9])\s*일", query):
        year, month, day = match.groups()
        month_value = int(month)
        day_value = int(day)
        month_day = f"{month_value:02d}-{day_value:02d}"
        terms.extend([month_day, f"-{month_day}"])
        if year:
            terms.append(f"{year}-{month_day}")
    for match in re.finditer(r"(?<!\d)(1[0-2]|0?[1-9])\s*월", query):
        month = int(match.group(1))
        terms.extend([f"-{month:02d}-", f"{dt.date.today().year}-{month:02d}"])
    for match in re.finditer(r"(20\d{2})\s*년", query):
        terms.append(match.group(1))
    return terms


def query_table_weights(query: str) -> dict[str, int]:
    normalized = query.replace(" ", "")
    weights = {
        "speeches": 0,
        "incidents": 0,
        "company_accidents": 0,
        "collection_runs": 0,
        "analysis_reports": 0,
    }
    if "주요인사" in normalized or "발언" in normalized:
        weights["speeches"] += 8
    if "중대재해" in normalized or "재해사례" in normalized:
        weights["incidents"] += 8
    if "당사사고" in normalized or "대응방향" in normalized or "사과문" in normalized:
        weights["company_accidents"] += 8
    if "수집" in normalized or "이력" in normalized:
        weights["collection_runs"] += 8
    if "종합분석" in normalized or "시사점" in normalized:
        weights["analysis_reports"] += 8
    return weights


def query_search_hints(query: str) -> dict[str, Any]:
    date_terms = date_search_terms(query)
    table_weights = query_table_weights(query)
    table_hints = [table for table, weight in table_weights.items() if weight]
    return {
        "date_terms": date_terms,
        "table_hints": table_hints,
        "note": "한국어 날짜 표현은 ISO 날짜 문자열과 비교하세요. 예: '5월'은 '-05-' 또는 '2026-05'와 일치합니다.",
    }


def row_search_text(row: dict[str, Any]) -> str:
    return " ".join(normalize_text_value(value) for value in row.values()).lower()


def evidence_from_row(table: str, row: dict[str, Any]) -> dict[str, str]:
    if table == "speeches":
        return {
            "table": "주요인사발언",
            "id": str(row.get("id") or ""),
            "date": str(row.get("speech_date") or ""),
            "title": str(row.get("source_title") or row.get("actor") or "주요인사발언"),
            "summary": str(row.get("quote") or ""),
            "source_url": str(row.get("source_url") or ""),
        }
    if table == "incidents":
        return {
            "table": "중대재해사례",
            "id": str(row.get("id") or ""),
            "date": str(row.get("accident_date") or ""),
            "title": str(row.get("source_title") or row.get("company_name") or "중대재해사례"),
            "summary": str(row.get("accident_summary") or ""),
            "source_url": str(row.get("source_url") or ""),
        }
    if table == "company_accidents":
        return {
            "table": "당사사고 대응방향",
            "id": str(row.get("id") or ""),
            "date": str(row.get("created_at") or ""),
            "title": str(row.get("incident_description") or "당사사고 대응 기록")[:80],
            "summary": str(row.get("response_direction") or row.get("apology_text") or ""),
            "source_url": "",
        }
    if table == "collection_runs":
        period = f"{row.get('started_on') or ''}~{row.get('ended_on') or ''}".strip("~")
        return {
            "table": "수집이력",
            "id": str(row.get("id") or ""),
            "date": str(row.get("created_at") or ""),
            "title": f"{row.get('prompt_type') or '수집'} {period}",
            "summary": f"상태: {row.get('status') or ''}, 신규: {row.get('item_count') or 0}, 중복: {row.get('skipped_count') or 0}",
            "source_url": "",
        }
    return {
        "table": "종합분석",
        "id": str(row.get("id") or ""),
        "date": str(row.get("created_at") or ""),
        "title": "종합분석",
        "summary": normalize_text_value(row.get("body")),
        "source_url": "",
    }


def local_data_search_answer(query: str, context: dict[str, Any]) -> dict[str, Any]:
    terms = search_terms(query)
    table_weights = query_table_weights(query)
    scored: list[tuple[int, dict[str, str]]] = []
    for table in ("speeches", "incidents", "company_accidents", "collection_runs", "analysis_reports"):
        for row in context.get(table, []):
            if not isinstance(row, dict):
                continue
            text = row_search_text(row)
            score = table_weights.get(table, 0)
            if query.lower() in text:
                score += 10
            score += sum(text.count(term) for term in terms)
            if score:
                scored.append((score, evidence_from_row(table, row)))
    scored.sort(key=lambda item: item[0], reverse=True)
    evidence = [item for _, item in scored[:6]]
    if not evidence:
        return {
            "answer": "저장된 데이터에서 질문과 직접 연결되는 내용을 찾지 못했습니다. 기간, 회사명, 인물명, 사고명 같은 단어를 포함해 다시 검색해 주세요.",
            "evidence": [],
            "generated_by": "local_fallback",
            "notice": "AI 검색을 실행하지 못해 저장 데이터의 키워드 일치 여부만 확인했습니다.",
        }
    lines = ["저장된 데이터에서 관련성이 높은 항목은 다음과 같습니다."]
    for item in evidence:
        date = f" ({item['date']})" if item.get("date") else ""
        lines.append(f"- {item['table']} #{item['id']}{date}: {item['title']}")
    return {
        "answer": "\n".join(lines),
        "evidence": evidence,
        "generated_by": "local_fallback",
        "notice": "AI 검색을 실행하지 못해 저장 데이터의 키워드 일치 결과를 표시했습니다.",
    }


def normalize_evidence(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    evidence: list[dict[str, str]] = []
    for item in value[:8]:
        if not isinstance(item, dict):
            continue
        evidence.append(
            {
                "table": str(item.get("table") or item.get("type") or ""),
                "id": str(item.get("id") or item.get("record_id") or ""),
                "date": str(item.get("date") or item.get("created_at") or ""),
                "title": str(item.get("title") or item.get("name") or ""),
                "summary": str(item.get("summary") or item.get("reason") or item.get("content") or ""),
                "source_url": str(item.get("source_url") or item.get("url") or ""),
            }
        )
    return evidence


def generate_data_search_answer(query: str) -> dict[str, Any]:
    context = database_search_context()
    search_hints = query_search_hints(query)
    system_prompt = (
        "당신은 앱 내부 SQLite 데이터베이스를 검색해 답하는 한국어 어시스턴트입니다. "
        "반드시 제공된 데이터 안에서만 답하고, 데이터에 없는 사실은 없다고 말하세요."
    )
    user_prompt = f"""
사용자 질문:
{query}

검색 보조 해석:
{json.dumps(search_hints, ensure_ascii=False)}

아래는 현재 앱 DB에서 읽은 저장 데이터입니다.
질문 의도에 맞는 데이터를 찾아 한국어로 직접 답하세요.
질문에 특정 탭/테이블이 언급되면 그 테이블의 데이터를 우선 사용하세요.
한국어 날짜 표현은 날짜 필드의 ISO 형식과 대응해서 찾으세요. 예를 들어 "5월"은 "2026-05-13" 같은 날짜와 일치합니다.
일치하는 데이터가 부족하면 부족하다고 말하고, 추측으로 채우지 마세요.

반드시 JSON 객체만 출력하세요. 키는 아래만 사용하세요.
- answer: 사용자 질문에 대한 자연스러운 답변. 필요한 경우 항목별로 줄바꿈.
- evidence: 답변 근거로 사용한 데이터 배열. 각 객체는 table, id, date, title, summary, source_url 필드를 사용.

저장 데이터:
{json.dumps(context, ensure_ascii=False)}
""".strip()
    provider = "openai"
    notice = ""
    try:
        result = call_openai_json(system_prompt, user_prompt)
    except Exception as exc:
        try:
            result = call_gemini_json(system_prompt, user_prompt)
            provider = "gemini_fallback"
            notice = f"OpenAI 검색 실패로 Gemini fallback을 사용했습니다. ({exc})"
        except Exception:
            return local_data_search_answer(query, context)
    return {
        "query": query,
        "answer": str(result.get("answer") or "").strip() or "저장된 데이터에서 답변할 내용을 찾지 못했습니다.",
        "evidence": normalize_evidence(result.get("evidence")),
        "generated_by": provider,
        "notice": notice,
    }


def is_openai_quota_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    body = str(getattr(exc, "body", "") or "")
    message = str(exc)
    combined = f"{body}\n{message}".lower()
    return status_code == 429 and (
        "insufficient_quota" in combined
        or "exceeded your current quota" in combined
        or "quota" in combined
    )


def call_openai_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(".env에 OPENAI_API_KEY가 없습니다.")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.25,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        if is_openai_quota_error(exc):
            raise OpenAIQuotaError(
                "OpenAI API quota가 소진되어 OpenAI 분석을 실행할 수 없습니다. "
                "OpenAI 결제/사용량 한도를 확인하거나 OPENAI_API_KEY를 교체해 주세요."
            ) from exc
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.25,
            )
        except Exception as retry_exc:
            if is_openai_quota_error(retry_exc):
                raise OpenAIQuotaError(
                    "OpenAI API quota가 소진되어 OpenAI 분석을 실행할 수 없습니다. "
                    "OpenAI 결제/사용량 한도를 확인하거나 OPENAI_API_KEY를 교체해 주세요."
                ) from retry_exc
            raise
    content = response.choices[0].message.content or "{}"
    return parse_json_object(content)


def normalize_text_value(value: Any) -> str:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed = ast.literal_eval(stripped)
            except (ValueError, SyntaxError):
                return stripped
            if isinstance(parsed, dict):
                return normalize_text_value(parsed)
        return stripped
    if isinstance(value, dict):
        preferred_keys = (
            "title",
            "content",
            "context",
            "direction",
            "response_direction",
            "effect",
            "action",
            "summary",
            "text",
        )
        parts: list[str] = []
        for key in preferred_keys:
            item = value.get(key)
            if item:
                text = normalize_text_value(item)
                if text:
                    parts.append(text)
        for key, item in value.items():
            if key in preferred_keys or not item:
                continue
            text = normalize_text_value(item)
            if text:
                parts.append(text)
        return "\n".join(dict.fromkeys(parts))
    if isinstance(value, list):
        return "\n".join(filter(None, (normalize_text_value(item) for item in value)))
    return str(value or "").strip()


def normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [text for item in value if (text := normalize_text_value(item))]
    if not value:
        return []
    text = normalize_text_value(value)
    return [text] if text else []


def clean_url(url: str) -> str:
    return url.strip().rstrip(".,;)]}")


bp.add_app_template_global(is_valid_article_url, "is_valid_article_url")


def generate_summary_analysis() -> dict[str, Any]:
    context = context_for_ai()
    system_prompt = (
        "당신은 한국 산업안전, 노동정책, 대기업 경영층 보고서 작성에 능숙한 전략 분석가입니다. "
        "모든 답변은 한국어로 작성하고, 사실관계가 불명확한 부분은 단정하지 마세요."
    )
    user_prompt = f"""
다음은 누적 저장된 주요인사 발언과 중대재해 사례 데이터입니다.
대통령, 노동부장관 등 정부 주요인사의 워딩과 타사 중대재해 흐름을 종합해
최근 노동/안전 정책 변화와 포스코그룹의 대응 방향을 경영층 보고 문장으로 정리하세요.

반드시 JSON 객체만 출력하세요. 키는 아래 2개만 사용하세요.
- key_implications: 주요 시사점 배열. 각 항목은 제목 1문장 + 근거/의미를 담은 2~4문장.
- posco_response: 포스코그룹 대응방안 배열. 각 항목은 실행 방향과 기대효과가 드러나는 2~4문장.

분석 포인트:
- 정부의 최근 안전/노동 관련 정책적 변화.
- 대통령/노동부장관 발언이 중대재해 또는 산업재해 이슈와 연결되는 방식.
- 타사 주요 중대재해 사례와 정부/노동부/수사기관 대외대응.
- 포스코가 AI 안전기술, 협력사/중소규모 사업장 지원, 예방 중심 안전관리, 대외 커뮤니케이션을 어떻게 조합해야 하는지.

데이터:
{json.dumps(context, ensure_ascii=False)}
""".strip()
    provider = "openai"
    notice = ""
    try:
        result = call_openai_json(system_prompt, user_prompt)
    except OpenAIQuotaError as exc:
        result = call_gemini_json(system_prompt, user_prompt)
        provider = "gemini_fallback"
        notice = f"{exc} Gemini API로 임시 분석을 생성했습니다."
    return {
        "key_implications": normalize_list(result.get("key_implications")),
        "posco_response": normalize_list(result.get("posco_response")),
        "generated_by": provider,
        "notice": notice,
    }


def generate_company_accident_response(incident_description: str) -> dict[str, str]:
    context = context_for_ai()
    incident_apologies = [
        {
            "company_name": row["company_name"],
            "accident_date": row["accident_date"],
            "apology_text": row["apology_text"],
        }
        for row in fetch_all(
            """
            SELECT company_name, accident_date, apology_text
            FROM incidents
            WHERE TRIM(COALESCE(apology_text, '')) <> ''
            ORDER BY id DESC
            LIMIT 30
            """
        )
    ]
    context["incident_apologies_entered_by_user"] = incident_apologies
    system_prompt = (
        "당신은 한국 대기업의 중대재해 위기대응, 언론 발표문, 정부 정책 대응 방향을 작성하는 전문가입니다. "
        "방어적 표현보다 책임, 유가족/피해자, 원인조사 협조, 재발방지, 현장 실행을 우선하세요."
    )
    user_prompt = f"""
포스코에서 다음 재해가 발생했다고 가정합니다.
입력 재해내용:
{incident_description}

누적 관리된 주요인사 발언, 중대재해사례, 기존 포스코 재해 사과문, 담당자가 직접 입력한 타사 사과문을 참고해
언론 배포용 사과문과 회사 대응 방향을 작성하세요.

반드시 JSON 객체만 출력하세요. 키는 아래 2개만 사용하세요.
- apology_text: 언론 배포용 사과문. 5~8문장. 최근 정부 안전정책 워딩을 자연스럽게 반영.
- response_direction: 최근 정부 안전정책 동향을 고려한 당사 대응 방향. 5~8개 문장 또는 문단.

참고 데이터:
{json.dumps(context, ensure_ascii=False)}
""".strip()
    try:
        result = call_openai_json(system_prompt, user_prompt)
    except OpenAIQuotaError as exc:
        result = call_gemini_json(system_prompt, user_prompt)
        result["notice"] = f"{exc} Gemini API로 임시 사과문과 대응방향을 생성했습니다."
    return {
        "apology_text": str(result.get("apology_text", "")).strip(),
        "response_direction": str(result.get("response_direction", "")).strip(),
        "notice": str(result.get("notice", "")).strip(),
    }


def latest_analysis() -> dict[str, Any] | None:
    row = fetch_one(
        "SELECT body, created_at FROM analysis_reports WHERE kind = 'summary' ORDER BY id DESC LIMIT 1"
    )
    if not row:
        return None
    try:
        body = json.loads(row["body"])
    except json.JSONDecodeError:
        body = {}
    body["key_implications"] = normalize_list(body.get("key_implications"))
    body["posco_response"] = normalize_list(body.get("posco_response"))
    body["created_at"] = row["created_at"]
    return body


def raw_payload_with_item(row: sqlite3.Row) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        payload = json.loads(row["raw_payload"] or "{}")
    except json.JSONDecodeError:
        payload = {}
    item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
    return payload, item


def repair_source_link(table: str, row: sqlite3.Row) -> bool:
    payload, item = raw_payload_with_item(row)
    if not item:
        item = dict(row)
    date_value = item_get(item, "speech_date", "accident_date", "date", "날짜", "사고일") or row[
        "speech_date" if table == "speeches" else "accident_date"
    ]
    item["source_title"] = row["source_title"] or item_get(item, "source_title", "title", "기사제목")
    item["source_url"] = row["source_url"] or item_get(item, "source_url", "url", "출처URL")
    item["source_name"] = row["source_name"] or item_get(item, "source_name", "media", "언론사", "플랫폼")
    source = normalized_primary_source(item, [], date_value or "")
    if not source["source_url"] or is_grounding_redirect_url(source["source_url"]):
        return False
    if (
        source["source_url"] == (row["source_url"] or "")
        and source["source_title"] == (row["source_title"] or "")
        and source["source_name"] == (row["source_name"] or "")
    ):
        return False
    payload["item"] = item
    with get_db() as db:
        db.execute(
            f"""
            UPDATE {table}
            SET source_title = ?, source_url = ?, source_name = ?, raw_payload = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                source["source_title"],
                source["source_url"],
                source["source_name"],
                json.dumps(payload, ensure_ascii=False),
                now_iso(),
                row["id"],
            ),
        )
    return True


def repair_all_source_links() -> tuple[int, int]:
    updated = 0
    failed = 0
    for table in ("speeches", "incidents"):
        rows = fetch_all(
            f"""
            SELECT * FROM {table}
            WHERE source_url LIKE '%vertexaisearch.cloud.google.com/grounding-api-redirect%'
               OR TRIM(COALESCE(source_url, '')) = ''
            ORDER BY id DESC
            """
        )
        for row in rows:
            try:
                if repair_source_link(table, row):
                    updated += 1
                elif is_grounding_redirect_url(row["source_url"] or ""):
                    failed += 1
            except Exception:
                failed += 1
    return updated, failed


def build_index_context(
    pending_collection: dict[str, Any] | None = None,
    pending_speech_collection: dict[str, Any] | None = None,
    pending_incident_collection: dict[str, Any] | None = None,
    data_search_query: str = "",
    data_search_result: dict[str, Any] | None = None,
    company_draft: dict[str, str] | None = None,
    active_tab: str = "analysis",
) -> dict[str, Any]:
    speeches = fetch_all(
        """
        SELECT * FROM speeches
        ORDER BY COALESCE(speech_date, '') DESC, id DESC
        """
    )
    incidents = fetch_all(
        """
        SELECT * FROM incidents
        ORDER BY COALESCE(accident_date, '') DESC, id DESC
        """
    )
    company_accidents = fetch_all(
        """
        SELECT * FROM company_accidents
        ORDER BY id DESC
        """
    )
    recent_speeches = fetch_all(
        """
        SELECT * FROM speeches
        ORDER BY COALESCE(speech_date, '') DESC, id DESC
        LIMIT 5
        """
    )
    recent_incidents = fetch_all(
        """
        SELECT * FROM incidents
        ORDER BY COALESCE(accident_date, '') DESC, id DESC
        LIMIT 5
        """
    )
    runs = fetch_all(
        """
        SELECT * FROM collection_runs
        ORDER BY id DESC
        LIMIT 6
        """
    )
    return {
        "speeches": speeches,
        "incidents": incidents,
        "company_accidents": company_accidents,
        "recent_speeches": recent_speeches,
        "recent_incidents": recent_incidents,
        "analysis": latest_analysis(),
        "runs": runs,
        "today": dt.date.today().isoformat(),
        "pending_collection": pending_collection,
        "pending_collection_json": json.dumps(pending_collection, ensure_ascii=False) if pending_collection else "",
        "pending_speech_collection": pending_speech_collection,
        "pending_speech_collection_json": json.dumps(pending_speech_collection, ensure_ascii=False) if pending_speech_collection else "",
        "pending_incident_collection": pending_incident_collection,
        "pending_incident_collection_json": json.dumps(pending_incident_collection, ensure_ascii=False) if pending_incident_collection else "",
        "data_search_query": data_search_query,
        "data_search_result": data_search_result,
        "company_draft": company_draft,
        "active_tab": active_tab,
    }


@bp.route("/")
def index() -> str:
    return render_template("proj2/index.html", **build_index_context())


@bp.post("/collect")
def collect() -> Response:
    try:
        started_on = parse_date(request.form.get("started_on", ""), "시작")
        ended_on = parse_date(request.form.get("ended_on", ""), "종료")
        if started_on > ended_on:
            raise ValueError("시작일은 종료일보다 늦을 수 없습니다.")
        pending_collection = extract_collection(started_on, ended_on)
        sections = pending_collection["sections"]
        parts = [f"{section['label']} {len(section['items'])}건" for section in sections.values()]
        flash("데이터 추출 완료: " + " / ".join(parts) + ". 확인 후 저장 버튼을 눌러 주세요.", "success")
        return render_template(
            "proj2/index.html",
            **build_index_context(pending_collection=pending_collection, active_tab="analysis"),
        )
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("proj2.index"))


@bp.post("/collection/save")
def collection_save() -> Response:
    try:
        payload = json.loads(request.form.get("collection_payload", "") or "{}")
        results = save_collection_payload(payload)
        parts = [f"{label} 신규 {inserted}건, 중복 {skipped}건" for label, (inserted, skipped) in results.items()]
        flash("데이터베이스 저장 완료: " + " / ".join(parts), "success")
    except Exception as exc:
        flash(f"데이터 저장 실패: {exc}", "danger")
    return redirect(url_for("proj2.index") + "#analysis")


@bp.post("/source-links/repair")
def source_links_repair() -> Response:
    try:
        updated, failed = repair_all_source_links()
        message = f"기사 링크 보정 완료: {updated}건 수정"
        if failed:
            message += f", {failed}건은 정확한 원문 URL을 찾지 못했습니다"
        flash(message, "success" if not failed else "warning")
    except Exception as exc:
        flash(f"기사 링크 보정 실패: {exc}", "danger")
    return redirect(url_for("proj2.index") + "#analysis")


# ------------------------------------------------------------------ #
#  데이터 추출 백그라운드 작업
#  Gemini grounded 호출이 길어 요청 스레드에서 직접 돌리면 gunicorn 워커
#  타임아웃(500)이 난다. 별도 스레드에서 실행하고 진행 페이지에서 폴링한다.
#  proj1 JOBS와 동일하게 단일 워커(-w 1) 전제에서 안전하다.
# ------------------------------------------------------------------ #
EXTRACT_JOBS: dict[str, dict[str, Any]] = {}
EXTRACT_LABELS = {"speeches": "주요인사발언", "incidents": "중대재해사례"}


def _run_extract_job(job_id: str, key: str, started_on: str, ended_on: str) -> None:
    try:
        pending = extract_collection_section(key, started_on, ended_on)
        job = EXTRACT_JOBS.get(job_id)
        if job is None:
            return
        job["result"] = pending
        job["item_count"] = len(pending["sections"][key]["items"])
        job["status"] = "done"
    except Exception as exc:
        job = EXTRACT_JOBS.get(job_id)
        if job is not None:
            job["error"] = str(exc)
            job["status"] = "error"


def start_extract_job(key: str) -> str:
    started_on = parse_date(request.form.get("started_on", ""), "시작")
    ended_on = parse_date(request.form.get("ended_on", ""), "종료")
    if started_on > ended_on:
        raise ValueError("시작일은 종료일보다 늦을 수 없습니다.")
    job_id = uuid.uuid4().hex
    EXTRACT_JOBS[job_id] = {
        "status": "running",
        "key": key,
        "label": EXTRACT_LABELS[key],
        "started_on": started_on,
        "ended_on": ended_on,
        "result": None,
        "error": None,
        "item_count": 0,
        "created_at": now_iso(),
    }
    threading.Thread(
        target=_run_extract_job,
        args=(job_id, key, started_on, ended_on),
        daemon=True,
    ).start()
    return job_id


@bp.get("/extract/progress/<job_id>")
def extract_progress(job_id: str) -> Response:
    job = EXTRACT_JOBS.get(job_id)
    if job is None:
        flash("추출 작업을 찾을 수 없습니다. 다시 시도해 주세요.", "warning")
        return redirect(url_for("proj2.index"))
    if job["status"] != "running":
        return redirect(url_for("proj2.extract_result", job_id=job_id))
    return render_template("proj2/extract_progress.html", job_id=job_id, job=job)


@bp.get("/extract/status/<job_id>")
def extract_status(job_id: str):
    job = EXTRACT_JOBS.get(job_id)
    if job is None:
        return {"status": "missing"}, 404
    return {
        "status": job["status"],
        "label": job["label"],
        "item_count": job["item_count"],
        "error": job["error"],
    }


@bp.get("/extract/result/<job_id>")
def extract_result(job_id: str) -> Response:
    job = EXTRACT_JOBS.get(job_id)
    if job is None:
        flash("추출 작업을 찾을 수 없습니다. 다시 시도해 주세요.", "warning")
        return redirect(url_for("proj2.index"))
    key = job["key"]
    anchor = "#speeches" if key == "speeches" else "#incidents"
    if job["status"] == "running":
        return redirect(url_for("proj2.extract_progress", job_id=job_id))
    if job["status"] == "error":
        error = job["error"]
        EXTRACT_JOBS.pop(job_id, None)
        flash(f"{EXTRACT_LABELS[key]} 추출 실패: {error}", "danger")
        return redirect(url_for("proj2.index") + anchor)
    pending = job["result"]
    item_count = job["item_count"]
    EXTRACT_JOBS.pop(job_id, None)
    flash(f"{EXTRACT_LABELS[key]} {item_count}건을 추출했습니다. 확인 후 저장 버튼을 눌러 주세요.", "success")
    context_kwargs = (
        {"pending_speech_collection": pending}
        if key == "speeches"
        else {"pending_incident_collection": pending}
    )
    return render_template(
        "proj2/index.html",
        **build_index_context(active_tab=key, **context_kwargs),
    )


@bp.post("/speeches/extract")
def speeches_extract() -> Response:
    try:
        job_id = start_extract_job("speeches")
    except Exception as exc:
        flash(str(exc), "danger")
        return redirect(url_for("proj2.index") + "#speeches")
    return redirect(url_for("proj2.extract_progress", job_id=job_id))


@bp.post("/speeches/save-extracted")
def speeches_save_extracted() -> Response:
    try:
        payload = json.loads(request.form.get("collection_payload", "") or "{}")
        results = save_collection_payload(payload)
        inserted, skipped = results.get("주요인사발언", (0, 0))
        flash(f"주요인사발언 저장 완료: 신규 {inserted}건, 중복 {skipped}건", "success")
    except Exception as exc:
        flash(f"주요인사발언 저장 실패: {exc}", "danger")
    return redirect(url_for("proj2.index") + "#speeches")


@bp.post("/speeches/upload-csv")
def speeches_upload_csv() -> Response:
    file = request.files.get("csv_file")
    if not file or not file.filename:
        flash("업로드할 CSV 파일을 선택해 주세요.", "warning")
        return redirect(url_for("proj2.index") + "#speeches")
    try:
        inserted, updated, skipped, empty = import_csv_items(file, SPEECH_CSV_MAPPING, upsert_speech_from_csv)
        message = f"주요인사발언 CSV 업로드 완료: 신규 {inserted}건, 갱신 {updated}건, 제외 {skipped}건"
        if empty:
            message += f", 빈 행 {empty}건 제외"
        flash(message, "success")
    except Exception as exc:
        flash(f"주요인사발언 CSV 업로드 실패: {exc}", "danger")
    return redirect(url_for("proj2.index") + "#speeches")


@bp.post("/incidents/extract")
def incidents_extract() -> Response:
    try:
        job_id = start_extract_job("incidents")
    except Exception as exc:
        flash(str(exc), "danger")
        return redirect(url_for("proj2.index") + "#incidents")
    return redirect(url_for("proj2.extract_progress", job_id=job_id))


@bp.post("/incidents/save-extracted")
def incidents_save_extracted() -> Response:
    try:
        payload = json.loads(request.form.get("collection_payload", "") or "{}")
        results = save_collection_payload(payload)
        inserted, skipped = results.get("중대재해사례", (0, 0))
        flash(f"중대재해사례 저장 완료: 신규 {inserted}건, 중복 {skipped}건", "success")
    except Exception as exc:
        flash(f"중대재해사례 저장 실패: {exc}", "danger")
    return redirect(url_for("proj2.index") + "#incidents")


@bp.post("/incidents/upload-csv")
def incidents_upload_csv() -> Response:
    file = request.files.get("csv_file")
    if not file or not file.filename:
        flash("업로드할 CSV 파일을 선택해 주세요.", "warning")
        return redirect(url_for("proj2.index") + "#incidents")
    try:
        inserted, updated, skipped, empty = import_csv_items(file, INCIDENT_CSV_MAPPING, upsert_incident_from_csv)
        message = f"중대재해사례 CSV 업로드 완료: 신규 {inserted}건, 갱신 {updated}건, 제외 {skipped}건"
        if empty:
            message += f", 빈 행 {empty}건 제외"
        flash(message, "success")
    except Exception as exc:
        flash(f"중대재해사례 CSV 업로드 실패: {exc}", "danger")
    return redirect(url_for("proj2.index") + "#incidents")


@bp.post("/data-search")
def data_search() -> Response:
    query = request.form.get("query", "").strip()
    if not query:
        flash("검색할 내용을 입력해 주세요.", "warning")
        return redirect(url_for("proj2.index") + "#data-search")
    result = generate_data_search_answer(query)
    return render_template(
        "proj2/index.html",
        **build_index_context(
            data_search_query=query,
            data_search_result=result,
            active_tab="data-search",
        ),
    )


@bp.post("/analysis/generate")
def analysis_generate() -> Response:
    try:
        body = generate_summary_analysis()
        with get_db() as db:
            db.execute(
                "INSERT INTO analysis_reports (kind, body, created_at) VALUES (?, ?, ?)",
                ("summary", json.dumps(body, ensure_ascii=False), now_iso()),
            )
        if body.get("generated_by") == "gemini_fallback":
            flash("OpenAI quota가 소진되어 Gemini fallback으로 종합분석을 생성했습니다.", "warning")
        else:
            flash("종합분석을 생성했습니다.", "success")
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("proj2.index") + "#analysis")


@bp.post("/speeches")
def speech_create() -> Response:
    flash("주요인사 발언 직접 추가 기능은 제거되었습니다. 기간별 데이터 추출 후 저장해 주세요.", "warning")
    return redirect(url_for("proj2.index") + "#speeches")


@bp.post("/speeches/<int:speech_id>/update")
def speech_update(speech_id: int) -> Response:
    with get_db() as db:
        db.execute(
            """
            UPDATE speeches
            SET speech_date = ?, actor = ?, organization = ?, venue = ?,
                quote = ?, keywords = ?, source_title = ?, source_url = ?,
                source_name = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                request.form.get("speech_date", "").strip(),
                request.form.get("actor", "").strip(),
                request.form.get("organization", "").strip(),
                request.form.get("venue", "").strip(),
                request.form.get("quote", "").strip(),
                request.form.get("keywords", "").strip(),
                request.form.get("source_title", "").strip(),
                request.form.get("source_url", "").strip(),
                request.form.get("source_name", "").strip(),
                now_iso(),
                speech_id,
            ),
        )
    flash("주요인사 발언을 수정했습니다.", "success")
    return redirect(url_for("proj2.index") + "#speeches")


@bp.post("/speeches/<int:speech_id>/delete")
def speech_delete(speech_id: int) -> Response:
    with get_db() as db:
        db.execute("DELETE FROM speeches WHERE id = ?", (speech_id,))
    flash("주요인사 발언을 삭제했습니다.", "success")
    return redirect(url_for("proj2.index") + "#speeches")


@bp.post("/incidents")
def incident_create() -> Response:
    flash("중대재해 사례 직접 추가 기능은 제거되었습니다. 기간별 데이터 추출 후 저장해 주세요.", "warning")
    return redirect(url_for("proj2.index") + "#incidents")


@bp.post("/incidents/<int:incident_id>/update")
def incident_update(incident_id: int) -> Response:
    with get_db() as db:
        db.execute(
            """
            UPDATE incidents
            SET company_name = ?, accident_date = ?, accident_summary = ?,
                external_response = ?, implication = ?, apology_text = ?,
                source_title = ?, source_url = ?, source_name = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                request.form.get("company_name", "").strip(),
                request.form.get("accident_date", "").strip(),
                request.form.get("accident_summary", "").strip(),
                request.form.get("external_response", "").strip(),
                request.form.get("implication", "").strip(),
                request.form.get("apology_text", "").strip(),
                request.form.get("source_title", "").strip(),
                request.form.get("source_url", "").strip(),
                request.form.get("source_name", "").strip(),
                now_iso(),
                incident_id,
            ),
        )
    flash("중대재해 사례를 수정했습니다.", "success")
    return redirect(url_for("proj2.index") + "#incidents")


@bp.post("/incidents/<int:incident_id>/delete")
def incident_delete(incident_id: int) -> Response:
    with get_db() as db:
        db.execute("DELETE FROM incidents WHERE id = ?", (incident_id,))
    flash("중대재해 사례를 삭제했습니다.", "success")
    return redirect(url_for("proj2.index") + "#incidents")


@bp.post("/company-accidents/generate")
def company_accident_generate() -> Response:
    description = request.form.get("incident_description", "").strip()
    if not description:
        flash("재해내용을 입력해 주세요.", "warning")
        return redirect(url_for("proj2.index") + "#response")
    try:
        result = generate_company_accident_response(description)
        company_draft = {
            "incident_description": description,
            "apology_text": result["apology_text"],
            "response_direction": result["response_direction"],
        }
        if result.get("notice"):
            flash("OpenAI quota가 소진되어 Gemini fallback으로 당사 사고 대응방향과 사과문을 생성했습니다. 검토 후 저장해 주세요.", "warning")
        else:
            flash("당사 사고 대응방향과 사과문을 생성했습니다. 검토 후 저장해 주세요.", "success")
        return render_template(
            "proj2/index.html",
            **build_index_context(company_draft=company_draft, active_tab="response"),
        )
    except Exception as exc:
        flash(str(exc), "danger")
    return redirect(url_for("proj2.index") + "#response")


@bp.post("/company-accidents")
def company_accident_save() -> Response:
    description = request.form.get("incident_description", "").strip()
    apology_text = request.form.get("apology_text", "").strip()
    response_direction = request.form.get("response_direction", "").strip()
    if not description:
        flash("재해내용을 입력해 주세요.", "warning")
        return redirect(url_for("proj2.index") + "#response")
    timestamp = now_iso()
    with get_db() as db:
        db.execute(
            """
            INSERT INTO company_accidents (
                incident_description, apology_text, response_direction,
                context_snapshot, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                description,
                apology_text,
                response_direction,
                json.dumps(context_for_ai(), ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
    flash("당사 사고 대응 기록을 저장했습니다.", "success")
    return redirect(url_for("proj2.index") + "#response")


@bp.post("/company-accidents/<int:accident_id>/update")
def company_accident_update(accident_id: int) -> Response:
    with get_db() as db:
        db.execute(
            """
            UPDATE company_accidents
            SET incident_description = ?, apology_text = ?, response_direction = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                request.form.get("incident_description", "").strip(),
                request.form.get("apology_text", "").strip(),
                request.form.get("response_direction", "").strip(),
                now_iso(),
                accident_id,
            ),
        )
    flash("당사 사고 대응 기록을 수정했습니다.", "success")
    return redirect(url_for("proj2.index") + "#response")


@bp.post("/company-accidents/<int:accident_id>/delete")
def company_accident_delete(accident_id: int) -> Response:
    with get_db() as db:
        db.execute("DELETE FROM company_accidents WHERE id = ?", (accident_id,))
    flash("당사 사고 대응 기록을 삭제했습니다.", "success")
    return redirect(url_for("proj2.index") + "#response")


def csv_response(filename: str, headers: list[tuple[str, str]], rows: list[sqlite3.Row]) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([label for _, label in headers])
    for row in rows:
        writer.writerow([row[key] or "" for key, _ in headers])
    payload = buffer.getvalue().encode("utf-8-sig")
    return Response(
        payload,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@bp.get("/speeches.csv")
def speeches_csv() -> Response:
    rows = fetch_all(
        """
        SELECT * FROM speeches
        ORDER BY COALESCE(speech_date, '') DESC, id DESC
        """
    )
    headers = [
        ("speech_date", "날짜"),
        ("actor", "대상인물"),
        ("organization", "기관"),
        ("venue", "발언장소"),
        ("quote", "주요발언내용"),
        ("keywords", "핵심키워드"),
        ("source_title", "주요발언기사출처"),
        ("source_url", "출처URL"),
        ("source_name", "출처명"),
    ]
    return csv_response("speeches.csv", headers, rows)


@bp.get("/incidents.csv")
def incidents_csv() -> Response:
    rows = fetch_all(
        """
        SELECT * FROM incidents
        ORDER BY COALESCE(accident_date, '') DESC, id DESC
        """
    )
    headers = [
        ("id", "순번"),
        ("company_name", "회사명"),
        ("accident_date", "사고일"),
        ("accident_summary", "사고내용"),
        ("external_response", "대외대응"),
        ("implication", "시사점"),
        ("apology_text", "사과문"),
        ("source_title", "대표출처"),
        ("source_url", "출처URL"),
        ("source_name", "출처명"),
    ]
    return csv_response("incidents.csv", headers, rows)


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-secret")
    app.config["JSON_AS_ASCII"] = False
    app.register_blueprint(bp)
    init_db()
    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5001")),
        debug=os.getenv("FLASK_ENV") == "development",
    )
