"""Chat endpoint: runs the agent pipeline and streams Server-Sent Events."""

from __future__ import annotations

from flask import Blueprint, Response, stream_with_context

from ..agents import orchestrator
from ..agents.base import AgentContext, Turn
from ..core.errors import ValidationError
from ..core.serialization import sse_event
from ..services import services
from .deps import parse_body, require_auth, session_id
from .schemas import ChatRequest

bp = Blueprint("chat", __name__)
bp.before_request(require_auth)


@bp.post("/chat")
def chat():
    svc = services()
    body = parse_body(ChatRequest)
    message = body.message.strip()
    if not message:
        raise ValidationError("Message cannot be empty.")
    if len(message) > svc.settings.max_message_chars:
        raise ValidationError(f"Message is longer than {svc.settings.max_message_chars} characters.")

    # Resolve everything that can fail with a proper HTTP status before streaming.
    connection = svc.connections.get(session_id())
    override = svc.registry.resolve_override(body.model)
    ctx = AgentContext(
        question=message,
        history=[Turn(t.role, t.content, t.sql) for t in body.history],
        connection=connection,
        llm=svc.llm,
        settings=svc.settings,
        model_override=override,
    )

    def stream():
        yield ": stream-open\n\n"
        for event, data in orchestrator.run(ctx):
            yield sse_event(event, data)

    return Response(
        stream_with_context(stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
