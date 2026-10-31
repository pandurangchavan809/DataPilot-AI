"""DataPilot AI backend: FastAPI application factory."""

from __future__ import annotations

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from .api import register_api
from .config import Settings, get_settings
from .core.errors import AppError
from .core.logging import configure_logging
from .core.middleware import BodySizeLimitMiddleware, CatchUnhandledErrorsMiddleware
from .services import Services

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 1 * 1024 * 1024


def _ensure_demo_db(settings: Settings) -> None:
    if "sqlite_demo" in settings.allowed_db_types and not settings.demo_db_path.exists():
        from scripts.seed_demo import initialize_top50_db

        initialize_top50_db(settings.demo_db_path)
        logger.info("Seeded demo database at %s", settings.demo_db_path)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status_code)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_logs=settings.is_production)

    # Docs live under /api so they also work behind the nginx /api proxy.
    app = FastAPI(
        title=settings.app_name,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    # The last middleware added runs first. CORS stays outermost, so errors keep their CORS headers.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_BODY_BYTES)
    app.add_middleware(CatchUnhandledErrorsMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_headers=["Content-Type", "X-Session-Id", "Authorization"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        max_age=600,
    )

    _ensure_demo_db(settings)
    svc = Services.build(settings)
    svc.auth.seed_demo_user()
    app.state.services = svc
    register_api(app)

    @app.exception_handler(AppError)
    def _app_error(_request: Request, exc: AppError):
        return JSONResponse(exc.to_dict(), status_code=exc.status_code)

    @app.exception_handler(HTTPException)
    def _http_error(_request: Request, exc: HTTPException):
        code = HTTPStatus(exc.status_code).phrase.lower().replace(" ", "_")
        return _error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    def _validation_error(_request: Request, exc: RequestValidationError):
        # Only the location and message: FastAPI's default reply echoes the input, which could hold a password.
        first = exc.errors()[0]
        if first.get("type") == "json_invalid":
            return _error(400, "validation_error", "Request body must be valid JSON.")
        location = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        message = first.get("msg", "Invalid input")
        return _error(400, "validation_error", f"{location}: {message}" if location else message)

    logger.info("%s started (env=%s)", settings.app_name, settings.app_env)
    return app
