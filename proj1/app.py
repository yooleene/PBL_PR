"""Application entrypoint for the Naver reporter article analyzer prototype."""

from naver_reporter_app import create_app

app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
