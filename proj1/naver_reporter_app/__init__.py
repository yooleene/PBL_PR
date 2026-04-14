"""Flask application factory."""

from flask import Flask

from naver_reporter_app.config import Config
from naver_reporter_app.extensions import db
from naver_reporter_app.logging_config import configure_logging
from naver_reporter_app.routes import web_bp


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(Config)

    configure_logging(app)
    db.init_app(app)
    app.register_blueprint(web_bp)

    with app.app_context():
        db.create_all()

    return app
