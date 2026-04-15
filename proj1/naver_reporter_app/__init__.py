"""Flask application factory."""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from naver_reporter_app.config import Config
from naver_reporter_app.extensions import db
from naver_reporter_app.logging_config import configure_logging
from naver_reporter_app.routes import web_bp

logger = logging.getLogger(__name__)


def _ensure_sqlite_parent_dir(app: Flask) -> None:
    """Create the parent directory for a file-backed SQLite database."""
    database_uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if not database_uri.startswith("sqlite:///") or database_uri == "sqlite:///:memory:":
        return

    raw_path = database_uri.removeprefix("sqlite:///")
    if not raw_path:
        return

    db_path = Path(raw_path)
    if not db_path.is_absolute():
        db_path = Path(app.instance_path) / raw_path
    db_path.parent.mkdir(parents=True, exist_ok=True)


def _warn_for_ephemeral_cloud_run_sqlite(app: Flask) -> None:
    """Warn when Cloud Run is using local SQLite storage."""
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:////tmp/"):
        logger.warning(
            "Cloud Run is using /tmp SQLite storage. Data will not persist across container restarts. "
            "Set DATABASE_URL to a managed database for production."
        )


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    configure_logging(app)
    _ensure_sqlite_parent_dir(app)
    _warn_for_ephemeral_cloud_run_sqlite(app)
    db.init_app(app)
    app.register_blueprint(web_bp)

    with app.app_context():
        db.create_all()

    return app
