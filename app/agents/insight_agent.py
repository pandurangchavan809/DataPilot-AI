"""Insight agent: streams a grounded natural-language answer from results."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator

from ..core.serialization import to_jsonable
from ..db.executor import QueryResult
from ..llm.registry import ModelRef
from .base import AgentContext
from .prompts import INSIGHT_SYSTEM

MAX_RESULT_CHARS = 8000


def _result_payload(result: QueryResult) -> str:
    rows = result.rows
    payload = json.dumps({"columns": result.columns, "rows": rows}, default=to_jsonable)
    while len(payload) > MAX_RESULT_CHARS and len(rows) > 5:
        rows = rows[: len(rows) // 2]
        payload = json.dumps({"columns": result.columns, "rows": rows}, default=to_jsonable)
    note = f"Showing {len(rows)} of {result.row_count} rows" + (" (result was truncated)" if result.truncated else "")
    return f"{note}\n{payload}"


def stream_insight(
    ctx: AgentContext,
    question: str,
    sql: str,
    result: QueryResult,
    with_chart: bool,
    on_model: Callable[[ModelRef], None],
) -> Iterator[str]:
    chart_note = "\nA chart of these results is shown to the user below your answer." if with_chart else ""
    messages = [
        {"role": "system", "content": INSIGHT_SYSTEM.format(chart_note=chart_note)},
        {
            "role": "user",
            "content": f"Question: {question}\n\nSQL:\n{sql}\n\nResults:\n{_result_payload(result)}",
        },
    ]
    yield from ctx.llm.stream(messages, role="fast", override=ctx.model_override, on_model=on_model)
