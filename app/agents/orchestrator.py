"""Agent orchestrator.

A small explicit state machine:

    route ─┬─ write   → refusal
           ├─ general/schema → conversational answer
           └─ data → schema → [sql → guard → execute] x (1 + retries) → chart? → insight

It yields (event, payload) tuples that the API layer streams as SSE.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator

from ..core.errors import AppError, LLMError, QueryExecutionError, UnsafeQueryError
from ..db.executor import execute_readonly
from ..db.guard import validate_readonly_sql
from ..db.introspect import render_table_index, render_tables
from ..llm.registry import ModelRef
from .base import AgentContext
from .insight_agent import stream_insight
from .prompts import DIALECT_NAMES, GENERAL_SYSTEM, WRITE_REFUSAL
from .router import route
from .schema_agent import select_tables
from .sql_agent import SqlAgent
from .viz_agent import build_chart_spec

logger = logging.getLogger(__name__)

Event = tuple[str, dict]


class StepTracker:
    def __init__(self) -> None:
        self._started: dict[str, float] = {}

    def start(self, step_id: str, label: str, kind: str) -> Event:
        self._started[step_id] = time.perf_counter()
        return "step", {"id": step_id, "kind": kind, "label": label, "status": "running"}

    def end(self, step_id: str, label: str, kind: str, status: str = "done", detail: str = "") -> Event:
        started = self._started.pop(step_id, time.perf_counter())
        return "step", {
            "id": step_id,
            "kind": kind,
            "label": label,
            "status": status,
            "detail": detail,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }


def _model_event(ref: ModelRef) -> Event:
    return "model", {"id": ref.id, "label": ref.label, "provider": ref.provider}


def run(ctx: AgentContext) -> Iterator[Event]:
    steps = StepTracker()
    try:
        yield steps.start("route", "Understanding your question", "route")
        decision = route(ctx)
        detail = f"Intent: {decision.intent}" + (" · chart requested" if decision.needs_chart else "")
        yield steps.end("route", "Understood your question", "route", detail=detail)

        if decision.intent == "write":
            yield "token", {"text": WRITE_REFUSAL}
        elif decision.intent in ("general", "schema"):
            yield from _conversational(ctx, steps)
        else:
            yield from _data_flow(ctx, steps, decision.question, decision.needs_chart, decision.chart_type)
    except AppError as exc:
        logger.warning("Agent run failed: %s", exc.message)
        yield "error", {"code": exc.code, "message": exc.message}
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected agent failure")
        yield "error", {"code": "internal_error", "message": "Something went wrong while processing your request."}
    yield "done", {"models": sorted(ctx.models_used)}


def _conversational(ctx: AgentContext, steps: StepTracker) -> Iterator[Event]:
    conn = ctx.connection
    system = GENERAL_SYSTEM.format(
        database=conn.config.display_name(),
        dialect=DIALECT_NAMES.get(conn.config.dialect, "SQL"),
        tables=render_table_index(conn.schema.tables[:80]),
    )
    messages = [{"role": "system", "content": system}, *ctx.history_messages(), {"role": "user", "content": ctx.question}]
    yield steps.start("answer", "Composing answer", "answer")
    models: list[ModelRef] = []
    for text in ctx.llm.stream(messages, role="fast", override=ctx.model_override, on_model=models.append):
        if models:
            ctx.models_used.add(models[0].id)
            yield _model_event(models.pop())
        yield "token", {"text": text}
    yield steps.end("answer", "Answer ready", "answer")


def _data_flow(
    ctx: AgentContext, steps: StepTracker, question: str, needs_chart: bool, chart_type: str | None
) -> Iterator[Event]:
    settings = ctx.settings
    conn = ctx.connection

    yield steps.start("schema", "Finding relevant tables", "schema")
    tables, how = select_tables(ctx, question)
    names = ", ".join(t.name for t in tables[:6]) + ("…" if len(tables) > 6 else "")
    yield steps.end("schema", f"Selected {len(tables)} table{'s' if len(tables) != 1 else ''}", "schema",
                    detail=f"{names} ({how})")

    agent = SqlAgent(ctx, question, render_tables(tables))
    result = None
    safe_sql = ""
    last_error = ""
    attempts = settings.max_sql_retries + 1
    for attempt in range(1, attempts + 1):
        sid = f"sql-{attempt}"
        label = "Writing SQL" if attempt == 1 else f"Fixing SQL (attempt {attempt})"
        yield steps.start(sid, label, "sql")
        draft = agent.draft() if attempt == 1 else agent.repair(last_error)
        if draft.cannot_answer:
            yield steps.end(sid, "Question not answerable", "sql", status="skipped", detail=draft.cannot_answer)
            yield "token", {"text": f"I couldn't answer that from this database: {draft.cannot_answer}"}
            return
        yield steps.end(sid, "SQL drafted" if attempt == 1 else "SQL revised", "sql", detail=draft.explanation)

        vid = f"guard-{attempt}"
        yield steps.start(vid, "Verifying query is read-only", "guard")
        try:
            safe_sql = validate_readonly_sql(draft.sql or "", conn.config.dialect, settings.query_row_limit)
        except UnsafeQueryError as exc:
            last_error = exc.message
            yield steps.end(vid, "Query rejected by guard", "guard", status="error", detail=exc.message)
            continue
        yield steps.end(vid, "Query is read-only", "guard")
        yield "sql", {"sql": safe_sql, "explanation": draft.explanation, "attempt": attempt}

        eid = f"execute-{attempt}"
        yield steps.start(eid, "Running query", "execute")
        try:
            result = execute_readonly(
                conn.engine, safe_sql, row_limit=settings.query_row_limit, timeout_seconds=settings.query_timeout_seconds
            )
        except QueryExecutionError as exc:
            last_error = exc.message
            yield steps.end(eid, "Query failed", "execute", status="error", detail=exc.message)
            continue
        plural = "row" if result.row_count == 1 else "rows"
        yield steps.end(eid, f"Fetched {result.row_count:,} {plural}", "execute",
                        detail=f"{result.elapsed_ms} ms" + (" · truncated" if result.truncated else ""))
        break

    if result is None:
        raise LLMError(f"I couldn't produce a working query after {attempts} attempts. Last error: {last_error}")

    yield "result", result.to_dict()

    chart = None
    if needs_chart:
        yield steps.start("chart", "Designing chart", "chart")
        chart = build_chart_spec(ctx, question, result, chart_type)
        if chart:
            yield "chart", chart
            yield steps.end("chart", f"{chart['type'].title()} chart ready", "chart")
        else:
            yield steps.end("chart", "Result isn't chartable", "chart", status="skipped",
                            detail="A chart needs a label column and at least one numeric column.")

    # Results are already delivered; an insight failure should degrade, not fail the answer.
    yield steps.start("insight", "Analysing results", "insight")
    models: list[ModelRef] = []
    emitted = False
    try:
        for text in stream_insight(ctx, question, safe_sql, result, chart is not None, models.append):
            if models:
                ctx.models_used.add(models[0].id)
                yield _model_event(models.pop())
            emitted = True
            yield "token", {"text": text}
    except LLMError as exc:
        logger.warning("Insight generation failed: %s", exc.message)
        if not emitted:
            yield "token", {"text": "_Insights are temporarily unavailable. The query results are shown below._"}
        yield steps.end("insight", "Insights unavailable", "insight", status="error", detail=exc.message)
        return
    yield steps.end("insight", "Insights ready", "insight")
