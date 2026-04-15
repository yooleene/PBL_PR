"""Application entrypoint for the Naver reporter article analyzer prototype."""

from __future__ import annotations

from naver_reporter_app import create_app

app = create_app()


if __name__ == "__main__":
    app.run(
        host=app.config["HOST"],
        port=app.config["PORT"],
        debug=app.config["DEBUG"],
    )
