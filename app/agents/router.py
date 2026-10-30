"""Router agent: intent classification and question rewriting."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from .base import AgentContext
from .prompts import ROUTER_SYSTEM

logger = logging.getLogger(__name__)

INTENTS = {"data", "schema", "write", "general"}
CHART_TYPES = {"bar", "line", "area", "pie", "scatter"}
CHART_WORDS = re.compile(r"\b(chart|graph|plot|visuali[sz]e|visuali[sz]ation|trend line|pie|histogram)\b", re.I)
WRITE_WORDS = re.compile(r"^\s*(insert|update|delete|drop|alter|truncate|create)\b", re.I)


@dataclass
class Route:
    intent: str
    needs_chart: bool
    chart_type: str | None
    question: str


def route(ctx: AgentContext) -> Route:
    heuristic_chart = bool(CHART_WORDS.search(ctx.question))
    messages = [
        {"role": "system", "content": ROUTER_SYSTEM},
        *ctx.history_messages(max_chars=600),
        {"role": "user", "content": ctx.question},
    ]
    try:
        data, model = ctx.llm.complete_json(messages, role="fast", override=ctx.model_override, temperature=0)
        ctx.models_used.add(model.id)
        intent = str(data.get("intent", "data")).lower()
        chart_type = str(data.get("chart_type") or "").lower()
        return Route(
            intent=intent if intent in INTENTS else "data",
            needs_chart=bool(data.get("needs_chart")) or heuristic_chart,
            chart_type=chart_type if chart_type in CHART_TYPES else None,
            question=str(data.get("question") or ctx.question).strip() or ctx.question,
        )
    except Exception as exc:  # noqa: BLE001 - degrade to heuristics
        logger.warning("Router fell back to heuristics: %s", exc)
        intent = "write" if WRITE_WORDS.search(ctx.question) else "data"
        return Route(intent, heuristic_chart, None, ctx.question)
