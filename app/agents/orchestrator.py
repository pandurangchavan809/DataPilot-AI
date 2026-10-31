"""Agent orchestrator, built as a LangGraph state graph.

    route ─┬─ write          → refuse
           ├─ general/schema → converse
           └─ data → select_schema → write_sql → guard → execute ─┬─ chart → insight
                                         ▲          │        │    └─ insight
                                         └── retry ─┴────────┘

Every stage is a node and every branch is a conditional edge. Nodes send progress through
LangGraph's stream writer, and run() yields it as (event, payload) tuples for the API to stream as SSE.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from typing import Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

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


class AgentState(TypedDict, total=False):
    ctx: AgentContext
    steps: StepTracker
    intent: str
    question: str
    needs_chart: bool
    chart_type: str | None
    agent: SqlAgent
    attempt: int
    draft: Any
    safe_sql: str
    last_error: str
    failed: bool
    result: Any
    chart: dict | None


def _model_event(ref: ModelRef) -> Event:
    return "model", {"id": ref.id, "label": ref.label, "provider": ref.provider}


# --- Nodes -------------------------------------------------------------------


def route_node(state: AgentState) -> dict:
    emit, steps = get_stream_writer(), state["steps"]
    emit(steps.start("route", "Understanding your question", "route"))
    decision = route(state["ctx"])
    detail = f"Intent: {decision.intent}" + (" · chart requested" if decision.needs_chart else "")
    emit(steps.end("route", "Understood your question", "route", detail=detail))
    return {
        "intent": decision.intent,
        "question": decision.question,
        "needs_chart": decision.needs_chart,
        "chart_type": decision.chart_type,
    }


def refuse_node(state: AgentState) -> dict:
    get_stream_writer()(("token", {"text": WRITE_REFUSAL}))
    return {}


def converse_node(state: AgentState) -> dict:
    emit, steps, ctx = get_stream_writer(), state["steps"], state["ctx"]
    conn = ctx.connection
    system = GENERAL_SYSTEM.format(
        database=conn.config.display_name(),
        dialect=DIALECT_NAMES.get(conn.config.dialect, "SQL"),
        tables=render_table_index(conn.schema.tables[:80]),
    )
    messages = [{"role": "system", "content": system}, *ctx.history_messages(), {"role": "user", "content": ctx.question}]
    emit(steps.start("answer", "Composing answer", "answer"))
    models: list[ModelRef] = []
    for text in ctx.llm.stream(messages, role="fast", override=ctx.model_override, on_model=models.append):
        if models:
            ctx.models_used.add(models[0].id)
            emit(_model_event(models.pop()))
        emit(("token", {"text": text}))
    emit(steps.end("answer", "Answer ready", "answer"))
    return {}


def select_schema_node(state: AgentState) -> dict:
    emit, steps, ctx = get_stream_writer(), state["steps"], state["ctx"]
    emit(steps.start("schema", "Finding relevant tables", "schema"))
    tables, how = select_tables(ctx, state["question"])
    names = ", ".join(t.name for t in tables[:6]) + ("…" if len(tables) > 6 else "")
    emit(steps.end("schema", f"Selected {len(tables)} table{'s' if len(tables) != 1 else ''}", "schema",
                   detail=f"{names} ({how})"))
    return {"agent": SqlAgent(ctx, state["question"], render_tables(tables)), "attempt": 0, "last_error": ""}


def write_sql_node(state: AgentState) -> dict:
    emit, steps = get_stream_writer(), state["steps"]
    attempt = state["attempt"] + 1
    sid = f"sql-{attempt}"
    emit(steps.start(sid, "Writing SQL" if attempt == 1 else f"Fixing SQL (attempt {attempt})", "sql"))
    agent = state["agent"]
    draft = agent.draft() if attempt == 1 else agent.repair(state["last_error"])
    if draft.cannot_answer:
        emit(steps.end(sid, "Question not answerable", "sql", status="skipped", detail=draft.cannot_answer))
        emit(("token", {"text": f"I couldn't answer that from this database: {draft.cannot_answer}"}))
    else:
        emit(steps.end(sid, "SQL drafted" if attempt == 1 else "SQL revised", "sql", detail=draft.explanation))
    return {"attempt": attempt, "draft": draft}


def guard_node(state: AgentState) -> dict:
    emit, steps, ctx = get_stream_writer(), state["steps"], state["ctx"]
    attempt, draft = state["attempt"], state["draft"]
    vid = f"guard-{attempt}"
    emit(steps.start(vid, "Verifying query is read-only", "guard"))
    try:
        safe_sql = validate_readonly_sql(draft.sql or "", ctx.connection.config.dialect, ctx.settings.query_row_limit)
    except UnsafeQueryError as exc:
        emit(steps.end(vid, "Query rejected by guard", "guard", status="error", detail=exc.message))
        return {"failed": True, "last_error": exc.message}
    emit(steps.end(vid, "Query is read-only", "guard"))
    emit(("sql", {"sql": safe_sql, "explanation": draft.explanation, "attempt": attempt}))
    return {"failed": False, "safe_sql": safe_sql}


def execute_node(state: AgentState) -> dict:
    emit, steps, ctx = get_stream_writer(), state["steps"], state["ctx"]
    eid = f"execute-{state['attempt']}"
    emit(steps.start(eid, "Running query", "execute"))
    try:
        result = execute_readonly(
            ctx.connection.engine,
            state["safe_sql"],
            row_limit=ctx.settings.query_row_limit,
            timeout_seconds=ctx.settings.query_timeout_seconds,
        )
    except QueryExecutionError as exc:
        emit(steps.end(eid, "Query failed", "execute", status="error", detail=exc.message))
        return {"failed": True, "last_error": exc.message}
    plural = "row" if result.row_count == 1 else "rows"
    emit(steps.end(eid, f"Fetched {result.row_count:,} {plural}", "execute",
                   detail=f"{result.elapsed_ms} ms" + (" · truncated" if result.truncated else "")))
    emit(("result", result.to_dict()))
    return {"failed": False, "result": result}


def give_up_node(state: AgentState) -> dict:
    raise LLMError(f"I couldn't produce a working query after {state['attempt']} attempts. Last error: {state['last_error']}")


def chart_node(state: AgentState) -> dict:
    emit, steps = get_stream_writer(), state["steps"]
    emit(steps.start("chart", "Designing chart", "chart"))
    chart = build_chart_spec(state["ctx"], state["question"], state["result"], state["chart_type"])
    if chart:
        emit(("chart", chart))
        emit(steps.end("chart", f"{chart['type'].title()} chart ready", "chart"))
    else:
        emit(steps.end("chart", "Result isn't chartable", "chart", status="skipped",
                       detail="A chart needs a label column and at least one numeric column."))
    return {"chart": chart}


def insight_node(state: AgentState) -> dict:
    # Results are already delivered; an insight failure should degrade, not fail the answer.
    emit, steps, ctx = get_stream_writer(), state["steps"], state["ctx"]
    emit(steps.start("insight", "Analysing results", "insight"))
    models: list[ModelRef] = []
    emitted = False
    has_chart = state.get("chart") is not None
    try:
        for text in stream_insight(ctx, state["question"], state["safe_sql"], state["result"], has_chart, models.append):
            if models:
                ctx.models_used.add(models[0].id)
                emit(_model_event(models.pop()))
            emitted = True
            emit(("token", {"text": text}))
    except LLMError as exc:
        logger.warning("Insight generation failed: %s", exc.message)
        if not emitted:
            emit(("token", {"text": "_Insights are temporarily unavailable. The query results are shown below._"}))
        emit(steps.end("insight", "Insights unavailable", "insight", status="error", detail=exc.message))
        return {}
    emit(steps.end("insight", "Insights ready", "insight"))
    return {}


# --- Conditional edges -------------------------------------------------------


def _after_route(state: AgentState) -> str:
    if state["intent"] == "write":
        return "refuse"
    return "converse" if state["intent"] in ("general", "schema") else "select_schema"


def _after_write_sql(state: AgentState) -> str:
    return END if state["draft"].cannot_answer else "guard"


def _retry_or_give_up(state: AgentState) -> str:
    return "write_sql" if state["attempt"] <= state["ctx"].settings.max_sql_retries else "give_up"


def _after_guard(state: AgentState) -> str:
    return _retry_or_give_up(state) if state["failed"] else "execute"


def _after_execute(state: AgentState) -> str:
    if state["failed"]:
        return _retry_or_give_up(state)
    return "chart" if state["needs_chart"] else "insight"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("route", route_node)
    graph.add_node("refuse", refuse_node)
    graph.add_node("converse", converse_node)
    graph.add_node("select_schema", select_schema_node)
    graph.add_node("write_sql", write_sql_node)
    graph.add_node("guard", guard_node)
    graph.add_node("execute", execute_node)
    graph.add_node("give_up", give_up_node)
    graph.add_node("chart", chart_node)
    graph.add_node("insight", insight_node)

    graph.add_edge(START, "route")
    graph.add_conditional_edges("route", _after_route, ["refuse", "converse", "select_schema"])
    graph.add_edge("refuse", END)
    graph.add_edge("converse", END)
    graph.add_edge("select_schema", "write_sql")
    graph.add_conditional_edges("write_sql", _after_write_sql, ["guard", END])
    graph.add_conditional_edges("guard", _after_guard, ["execute", "write_sql", "give_up"])
    graph.add_conditional_edges("execute", _after_execute, ["chart", "insight", "write_sql", "give_up"])
    graph.add_edge("chart", "insight")
    graph.add_edge("insight", END)
    return graph.compile()


GRAPH = build_graph()


def run(ctx: AgentContext) -> Iterator[Event]:
    # Each SQL attempt can visit 3 nodes; the rest of the graph needs a handful more.
    limit = 3 * (ctx.settings.max_sql_retries + 1) + 8
    try:
        yield from GRAPH.stream(
            {"ctx": ctx, "steps": StepTracker()}, config={"recursion_limit": limit}, stream_mode="custom"
        )
    except AppError as exc:
        logger.warning("Agent run failed: %s", exc.message)
        yield "error", {"code": exc.code, "message": exc.message}
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected agent failure")
        yield "error", {"code": "internal_error", "message": "Something went wrong while processing your request."}
    yield "done", {"models": sorted(ctx.models_used)}
