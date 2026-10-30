"""Schema agent: picks the relevant subset of a schema for the SQL agent."""

from __future__ import annotations

import logging
import re

from ..db.introspect import Table, load_samples, render_table_index
from .base import AgentContext
from .prompts import SCHEMA_SELECT_SYSTEM

logger = logging.getLogger(__name__)

MAX_SAMPLED_TABLES = 8


def _with_related(selected: list[Table], all_tables: list[Table]) -> list[Table]:
    """Add tables referenced by foreign keys so joins remain possible."""
    by_name = {t.name.lower(): t for t in all_tables}
    result = {t.name.lower(): t for t in selected}
    for table in selected:
        for fk in table.foreign_keys:
            ref = by_name.get(fk.ref_table.lower())
            if ref:
                result.setdefault(ref.name.lower(), ref)
    return list(result.values())


def _keyword_match(question: str, tables: list[Table]) -> list[Table]:
    words = {w for w in re.findall(r"[a-z0-9]+", question.lower()) if len(w) > 2}

    def score(t: Table) -> int:
        tokens = set(re.findall(r"[a-z0-9]+", t.name.lower()))
        for c in t.columns:
            tokens.update(re.findall(r"[a-z0-9]+", c.name.lower()))
        return sum(1 for w in words for tok in tokens if w in tok or tok in w)

    ranked = sorted(tables, key=score, reverse=True)
    return [t for t in ranked[:6] if score(t) > 0] or ranked[:6]


def select_tables(ctx: AgentContext, question: str) -> tuple[list[Table], str]:
    """Return (tables, how) where ``how`` describes the selection strategy."""
    schema = ctx.connection.schema
    tables = schema.tables
    if len(tables) <= ctx.settings.schema_full_context_max_tables:
        selected, how = tables, "full schema"
    else:
        messages = [
            {"role": "system", "content": SCHEMA_SELECT_SYSTEM},
            {"role": "user", "content": f"Tables:\n{render_table_index(tables)}\n\nQuestion: {question}"},
        ]
        try:
            data, model = ctx.llm.complete_json(messages, role="fast", override=ctx.model_override, temperature=0)
            ctx.models_used.add(model.id)
            names = [str(n) for n in data.get("tables", [])]
            selected = [t for n in names if (t := schema.table(n))]
            how = "llm selection"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Schema selection fell back to keyword match: %s", exc)
            selected = []
        if not selected:
            selected, how = _keyword_match(question, tables), "keyword match"
        selected = _with_related(selected, tables)

    for table in selected[:MAX_SAMPLED_TABLES]:
        load_samples(
            ctx.connection.engine, table, ctx.settings.schema_sample_rows, ctx.settings.query_timeout_seconds
        )
    return selected, how
