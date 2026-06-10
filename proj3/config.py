import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
load_dotenv(ROOT_DIR / ".env", override=True)


def _bool_env(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _path_env(name, default):
    return Path(os.environ.get(name, default)).expanduser().resolve()


DATA_DIR = _path_env("APP_DATA_DIR", BASE_DIR / "data")
UPLOAD_DIR = _path_env("APP_UPLOAD_DIR", DATA_DIR / "uploads")
CHROMA_DIR = _path_env("APP_CHROMA_DIR", DATA_DIR / "chroma_db")
TASK_DB_PATH = _path_env("APP_TASK_DB", DATA_DIR / "tasks.sqlite3")


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "posco-module3-dev-secret-key")
    HOST = os.environ.get("APP_HOST", "127.0.0.1")
    PORT = _int_env("APP_PORT", 5001)
    DEBUG = _bool_env("APP_DEBUG", False) or _bool_env("FLASK_DEBUG", False)
    DATA_DIR = DATA_DIR
    UPLOAD_DIR = UPLOAD_DIR
    CHROMA_DIR = CHROMA_DIR
    TASK_DB_PATH = TASK_DB_PATH
    NAVER_USER_AGENT = os.environ.get(
        "APP_USER_AGENT",
        (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    )
