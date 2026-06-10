import hmac
import os
from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)


auth_bp = Blueprint("auth", __name__, template_folder="templates")


def _env(name: str, default: str = "") -> str:
    return str(current_app.config.get(name) or os.getenv(name, default))


def _configured_accounts() -> list[dict[str, str]]:
    return [
        {
            "id": _env("ADMIN_ID"),
            "password": _env("ADMIN_PASSWORD"),
            "role": "admin",
            "label": "관리자",
        },
        {
            "id": _env("USER_ID"),
            "password": _env("USER_PASSWORD"),
            "role": "user",
            "label": "일반 사용자",
        },
    ]


def _safe_next_url(value: str | None) -> str:
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return url_for("index")


def current_user() -> dict[str, str] | None:
    return session.get("user")


def is_logged_in() -> bool:
    return current_user() is not None


def is_admin() -> bool:
    user = current_user()
    return bool(user and user.get("role") == "admin")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_logged_in():
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for("auth.login", next=next_url))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_logged_in():
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for("auth.login", next=next_url))
        if not is_admin():
            abort(403)
        return view(*args, **kwargs)

    return wrapped


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        for account in _configured_accounts():
            if not account["id"] or not account["password"]:
                continue
            user_matches = hmac.compare_digest(username, account["id"])
            password_matches = hmac.compare_digest(password, account["password"])
            if user_matches and password_matches:
                session.clear()
                session["user"] = {
                    "id": account["id"],
                    "role": account["role"],
                    "label": account["label"],
                }
                session.permanent = True
                return redirect(_safe_next_url(request.args.get("next")))

        flash("아이디 또는 비밀번호가 올바르지 않습니다.", "danger")

    if is_logged_in():
        return redirect(_safe_next_url(request.args.get("next")))

    return render_template("login.html")


@auth_bp.post("/logout")
def logout():
    session.clear()
    flash("로그아웃되었습니다.", "success")
    return redirect(url_for("auth.login"))
