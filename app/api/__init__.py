"""API router registration."""

from __future__ import annotations

from fastapi import FastAPI

from . import auth, chat, connections, meta


def register_api(app: FastAPI) -> None:
    for router in (meta.router, meta.private_router, connections.router, chat.router):
        app.include_router(router, prefix="/api")
    app.include_router(auth.router, prefix="/api/auth")
