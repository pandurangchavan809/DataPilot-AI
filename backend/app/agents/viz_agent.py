"""Visualisation agent: produces a declarative chart spec (never code)."""

from __future__ import annotations

import json
import logging
import re

from ..core.serialization import to_jsonable
from ..db.executor import QueryResult
from .base import AgentContext
from .prompts import VIZ_SYSTEM

logger = logging.getLogger(__name__)

CHART_TYPES = {"bar", "line", "area", "pie", "scatter"}
TIME_HINT = re.compile(r"(year|date|month|day|time|quarter|week|period)", re.I)
MAX_CHART_POINTS = 500


def _heuristic(result: QueryResult, preferred: str | None) -> dict | None:
    numeric = [c for c, t in zip(result.columns, result.column_types) if t == "number"]
    other = [c for c, t in zip(result.columns, result.column_types) if t != "number"]
    if not numeric:
        return None
    time_cols = [c for c in result.columns if TIME_HINT.search(c)]
    x = (time_cols or other or [result.columns[0]])[0]
    y = [c for c in numeric if c != x][:3]
    if not y:
        return None
    kind = preferred or ("line" if x in time_cols else "bar")
    if kind == "pie" and (len(y) > 1 or result.row_count > 8):
        kind = "bar"
    return {"type": kind, "x": x, "y": y, "title": ""}


def _validate(spec: dict, result: QueryResult) -> dict | None:
    types = dict(zip(result.columns, result.column_types))
    kind = str(spec.get("type", "")).lower()
    x = spec.get("x")
    y = spec.get("y") or []
    if isinstance(y, str):
        y = [y]
    y = [c for c in y if types.get(c) == "number" and c != x][:3]
    if kind not in CHART_TYPES or x not in types or not y:
        return None
    return {"type": kind, "x": x, "y": y, "title": str(spec.get("title") or "")[:120]}


def build_chart_spec(ctx: AgentContext, question: str, result: QueryResult, preferred: str | None) -> dict | None:
    if result.row_count == 0 or len(result.columns) < 2:
        return None
    sample = {
        "columns": [{"name": c, "type": t} for c, t in zip(result.columns, result.column_types)],
        "row_count": result.row_count,
        "sample_rows": result.rows[:8],
    }
    hint = f"\nThe user prefers a {preferred} chart." if preferred else ""
    messages = [
        {"role": "system", "content": VIZ_SYSTEM},
        {"role": "user", "content": f"Question: {question}{hint}\n\nResult:\n{json.dumps(sample, default=to_jsonable)}"},
    ]
    spec = None
    try:
        data, model = ctx.llm.complete_json(messages, role="fast", override=ctx.model_override, temperature=0)
        ctx.models_used.add(model.id)
        spec = _validate(data, result)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Viz agent fell back to heuristics: %s", exc)
    spec = spec or _heuristic(result, preferred)
    if spec:
        spec["max_points"] = MAX_CHART_POINTS
    return spec
