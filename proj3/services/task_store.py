import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

try:
    from ..config import TASK_DB_PATH
except ImportError:
    from config import TASK_DB_PATH


_init_lock = threading.Lock()
_initialized = False


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect():
    TASK_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(TASK_DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def _db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_db():
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        with _db() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_tasks (
                    task_id TEXT PRIMARY KEY,
                    status_step INTEGER NOT NULL DEFAULT 0,
                    status_msg TEXT NOT NULL DEFAULT '대기 중...',
                    result_json TEXT,
                    ready INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
        _initialized = True


def create_task(task_id, keyword, company_name):
    _ensure_db()
    now = _now()
    payload = {
        "keyword": keyword,
        "company_name": company_name,
        "ready": False,
    }
    with _db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO analysis_tasks
                (task_id, status_step, status_msg, result_json, ready, created_at, updated_at)
            VALUES (?, 0, '대기 중...', ?, 0, ?, ?)
            """,
            (task_id, json.dumps(payload, ensure_ascii=False), now, now),
        )


def set_status(task_id, step, msg):
    _ensure_db()
    with _db() as conn:
        conn.execute(
            """
            UPDATE analysis_tasks
               SET status_step = ?, status_msg = ?, updated_at = ?
             WHERE task_id = ?
            """,
            (step, msg, _now(), task_id),
        )


def get_status(task_id):
    _ensure_db()
    with _db() as conn:
        row = conn.execute(
            "SELECT status_step, status_msg FROM analysis_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    if not row:
        return {"step": 0, "msg": "대기 중..."}
    return {"step": row["status_step"], "msg": row["status_msg"]}


def set_result(task_id, result):
    _ensure_db()
    ready = 1 if result.get("ready") else 0
    with _db() as conn:
        conn.execute(
            """
            UPDATE analysis_tasks
               SET result_json = ?, ready = ?, updated_at = ?
             WHERE task_id = ?
            """,
            (json.dumps(result, ensure_ascii=False), ready, _now(), task_id),
        )


def update_result(task_id, updates):
    current = get_result(task_id) or {}
    current.update(updates)
    set_result(task_id, current)
    return current


def get_result(task_id):
    _ensure_db()
    with _db() as conn:
        row = conn.execute(
            "SELECT result_json, ready FROM analysis_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    if not row or not row["result_json"]:
        return None

    result = json.loads(row["result_json"])
    result["ready"] = bool(row["ready"])
    return result
