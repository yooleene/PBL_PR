"""Logging setup."""

from __future__ import annotations

from logging.config import dictConfig

from flask import Flask


def configure_logging(app: Flask) -> None:
    """Configure application logging."""
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "level": app.config.get("LOG_LEVEL", "INFO"),
                }
            },
            "root": {
                "handlers": ["console"],
                "level": app.config.get("LOG_LEVEL", "INFO"),
            },
        }
    )
