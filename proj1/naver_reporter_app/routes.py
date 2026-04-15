"""Flask routes."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, render_template, request
from pydantic import ValidationError

from naver_reporter_app.schemas import AnalyzeRequest
from naver_reporter_app.services.collector import ReporterAnalysisService

logger = logging.getLogger(__name__)

web_bp = Blueprint("web", __name__)


@web_bp.get("/")
def index():
    """Render the input form."""
    return render_template("index.html")


@web_bp.get("/healthz")
def healthz():
    """Lightweight health endpoint for Cloud Run and local smoke tests."""
    return jsonify({"status": "ok"}), 200


@web_bp.post("/analyze")
def analyze_form():
    """Process form submission and render HTML results."""
    form_data = {
        "office_name": request.form.get("office_name", ""),
        "reporter_name": request.form.get("reporter_name", ""),
        "date_from": request.form.get("date_from", ""),
        "date_to": request.form.get("date_to", ""),
        "limit": request.form.get("limit", "20"),
    }
    try:
        payload = AnalyzeRequest.model_validate(form_data)
        response = ReporterAnalysisService().run(payload)
    except ValidationError as exc:
        return render_template("index.html", error=exc.errors(), form_data=form_data), 400
    except Exception as exc:  # pragma: no cover - network path
        logger.exception("Analysis failed")
        return render_template("index.html", error=str(exc), form_data=form_data), 500
    return render_template("result.html", result=response.model_dump())


@web_bp.post("/api/v1/analyze")
def analyze_api():
    """Run analysis through JSON API."""
    try:
        payload = AnalyzeRequest.model_validate(request.get_json(force=True, silent=False))
        response = ReporterAnalysisService().run(payload)
    except ValidationError as exc:
        return jsonify({"error": exc.errors()}), 400
    except Exception as exc:  # pragma: no cover - network path
        logger.exception("API analysis failed")
        return jsonify({"error": str(exc)}), 500
    return jsonify(response.model_dump())
