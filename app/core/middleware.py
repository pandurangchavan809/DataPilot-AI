"""Small ASGI middlewares. Plain ASGI, so they never buffer the SSE stream."""

from __future__ import annotations

import json
import logging

from fastapi import HTTPException

logger = logging.getLogger(__name__)


class BodySizeLimitMiddleware:
    """Rejects request bodies over the limit as they are read, with or without Content-Length."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        total = 0

        async def limited_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                raise HTTPException(413, "Request body is too large.")
            return message

        await self.app(scope, limited_receive, send)


class CatchUnhandledErrorsMiddleware:
    """Turns unexpected errors into our JSON format.

    FastAPI's own handler for Exception runs outside CORSMiddleware, so the browser
    would see a CORS failure instead of the error. This one runs inside it.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def tracking_send(message):
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:
            logger.exception("Unhandled error")
            if started:
                raise
            body = json.dumps({"error": {"code": "internal_error", "message": "Internal server error."}}).encode()
            headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
            await send({"type": "http.response.start", "status": 500, "headers": headers})
            await send({"type": "http.response.body", "body": body})
