"""DataPilot AI backend: Flask application factory."""

from __future__ import annotations

import logging

from flask import Flask, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from .api import register_api
from .config import Settings, get_settings
from .core.errors import AppError
from .core.logging import configure_logging
from .services import Services

logger = logging.getLogger(__name__)


def _ensure_demo_db(settings: Settings) -> None:
    if "sqlite_demo" in settings.allowed_db_types and not settings.demo_db_path.exists():
        from scripts.seed_demo import initialize_top50_db

        initialize_top50_db(settings.demo_db_path)
        logger.info("Seeded demo database at %s", settings.demo_db_path)


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_logs=settings.is_production)

    app = Flask(__name__)
    app.config.update(SECRET_KEY=settings.secret_key, JSON_SORT_KEYS=False, MAX_CONTENT_LENGTH=1 * 1024 * 1024)
    if settings.proxy_fix_hops:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=settings.proxy_fix_hops, x_proto=settings.proxy_fix_hops)

    CORS(
        app,
        resources={r"/api/*": {"origins": settings.cors_origins}},
        allow_headers=["Content-Type", "X-Session-Id"],
        methods=["GET", "POST", "DELETE", "OPTIONS"],
        max_age=600,
    )
    limiter = Limiter(get_remote_address, app=app, storage_uri=settings.rate_limit_storage_uri)

    _ensure_demo_db(settings)
    app.extensions["datapilot"] = Services.build(settings)
    register_api(app, limiter, settings.rate_limit)

    @app.errorhandler(AppError)
    def _app_error(exc: AppError):
        return jsonify(exc.to_dict()), exc.status_code

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        code = (exc.name or "error").lower().replace(" ", "_")
        return jsonify({"error": {"code": code, "message": exc.description}}), exc.code

    @app.errorhandler(Exception)
    def _unhandled(exc: Exception):
        logger.exception("Unhandled error")
        return jsonify({"error": {"code": "internal_error", "message": "Internal server error."}}), 500

    logger.info("%s started (env=%s)", settings.app_name, settings.app_env)
    return app
