"""API blueprint registration."""

from __future__ import annotations

from flask import Flask
from flask_limiter import Limiter

from . import auth, chat, connections, meta


def register_api(app: Flask, limiter: Limiter, rate_limit: str, auth_rate_limit: str) -> None:
    limiter.limit(rate_limit)(chat.bp)
    limiter.limit(rate_limit)(connections.bp)
    limiter.limit(auth_rate_limit)(auth.bp)  # slows down password guessing
    for bp in (meta.bp, meta.private_bp, connections.bp, chat.bp):
        app.register_blueprint(bp, url_prefix="/api")
    app.register_blueprint(auth.bp, url_prefix="/api/auth")
