"""Chat endpoint: runs the agent pipeline and streams Server-Sent Events."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..agents import orchestrator
from ..agents.base import AgentContext, Turn
from ..core.errors import ValidationError
from ..core.serialization import sse_event
from ..services import Services, get_services
from .deps import rate_limited, session_id
from .schemas import ChatRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"], dependencies=[Depends(rate_limited("rate_limit"))])


async def stream_events(ctx: AgentContext) -> AsyncIterator[str]:
    """Runs the agents on one thread of their own and forwards their events as SSE text.

    The graph blocks on LLM and DB calls, so it can't run on the event loop. It stays on a single
    thread because LangGraph's context can't move between threads part-way through a run. When the
    client disconnects, the stop flag ends the run at its next event, so no more LLM calls are paid for.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    stop = threading.Event()

    def worker() -> None:
        try:
            events = orchestrator.run(ctx)
            try:
                for item in events:
                    if stop.is_set():
                        break
                    loop.call_soon_threadsafe(queue.put_nowait, item)
            finally:
                events.close()
        except Exception:  # noqa: BLE001
            logger.exception("Agent worker failed")
        finally:
            # Always signal the end, whatever failed above, so the stream can never hang.
            try:
                loop.call_soon_threadsafe(queue.put_nowait, None)
            except RuntimeError:
                pass  # the server is shutting down

    threading.Thread(target=worker, daemon=True).start()
    try:
        yield ": stream-open\n\n"
        while (item := await queue.get()) is not None:
            yield sse_event(*item)
    finally:
        stop.set()


@router.post("/chat")
def chat(body: ChatRequest, sid: str = Depends(session_id), svc: Services = Depends(get_services)):
    message = body.message.strip()
    if not message:
        raise ValidationError("Message cannot be empty.")
    if len(message) > svc.settings.max_message_chars:
        raise ValidationError(f"Message is longer than {svc.settings.max_message_chars} characters.")

    # Resolve everything that can fail with a proper HTTP status before streaming.
    connection = svc.connections.get(sid)
    override = svc.registry.resolve_override(body.model)
    ctx = AgentContext(
        question=message,
        history=[Turn(t.role, t.content, t.sql) for t in body.history],
        connection=connection,
        llm=svc.llm,
        settings=svc.settings,
        model_override=override,
    )
    return StreamingResponse(
        stream_events(ctx),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
