import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, url_for

from auth import auth_bp, current_user, is_admin, is_logged_in, login_required


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "change-this-secret"),
        JSON_AS_ASCII=False,
        ADMIN_ID=os.getenv("ADMIN_ID", ""),
        ADMIN_PASSWORD=os.getenv("ADMIN_PASSWORD", ""),
        USER_ID=os.getenv("USER_ID", ""),
        USER_PASSWORD=os.getenv("USER_PASSWORD", ""),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=int(os.getenv("SESSION_HOURS", "8"))),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=_bool_env("SESSION_COOKIE_SECURE", False),
    )

    app.register_blueprint(auth_bp)

    from proj1.app import bp as proj1_bp
    from proj2.app import bp as proj2_bp, init_db as init_proj2_db
    from proj3.app import bp as proj3_bp

    app.register_blueprint(proj1_bp, url_prefix="/proj1")
    app.register_blueprint(proj2_bp, url_prefix="/proj2")
    app.register_blueprint(proj3_bp, url_prefix="/proj3")

    init_proj2_db()

    @app.before_request
    def require_login_for_internal_pages():
        endpoint = request.endpoint or ""
        public_endpoint = endpoint in {"auth.login", "static"} or endpoint.endswith(".static")
        if public_endpoint:
            return None
        if not is_logged_in():
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for("auth.login", next=next_url))
        return None

    @app.context_processor
    def inject_auth_state():
        return {
            "current_user": current_user(),
            "is_admin": is_admin(),
        }

    @app.route("/")
    @login_required
    def index():
        return render_template("index.html")

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("403.html"), 403

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", "5001")),
        debug=_bool_env("FLASK_DEBUG", False),
    )
