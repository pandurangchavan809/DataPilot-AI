"""SQL agent: writes (and repairs) dialect-specific read-only SQL."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..core.errors import LLMError
from .base import AgentContext
from .prompts import DIALECT_NAMES, SQL_RETRY_USER, SQL_SYSTEM

SQL_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
EXPLANATION = re.compile(r"Explanation:\s*(.+)", re.IGNORECASE)
CANNOT = re.compile(r"CANNOT_ANSWER:\s*(.+)", re.IGNORECASE | re.DOTALL)


@dataclass
class SqlDraft:
    sql: str | None
    explanation: str
    cannot_answer: str | None = None


def parse_sql_response(text: str) -> SqlDraft:
    cannot = CANNOT.search(text)
    fenced = SQL_FENCE.search(text)
    if cannot and not fenced:
        return SqlDraft(None, "", cannot.group(1).strip().splitlines()[0])
    if fenced:
        sql = fenced.group(1).strip()
    else:
        start = re.search(r"\b(WITH|SELECT)\b", text, re.IGNORECASE)
        if not start:
            raise LLMError("SQL agent did not return a query.")
        sql = EXPLANATION.split(text[start.start():])[0].strip()
    explanation = EXPLANATION.search(text)
    return SqlDraft(sql.rstrip(";").strip(), explanation.group(1).strip() if explanation else "")


class SqlAgent:
    """Keeps the conversation so repair attempts see their own failed SQL."""

    def __init__(self, ctx: AgentContext, question: str, schema_text: str):
        self.ctx = ctx
        dialect = DIALECT_NAMES.get(ctx.connection.config.dialect, "SQL")
        self.messages = [
            {"role": "system", "content": SQL_SYSTEM.format(dialect=dialect, schema=schema_text)},
            *ctx.history_messages(),
            {"role": "user", "content": question},
        ]

    def _ask(self) -> SqlDraft:
        result = self.ctx.llm.complete(self.messages, role="reasoning", override=self.ctx.model_override)
        self.ctx.models_used.add(result.model.id)
        self.messages.append({"role": "assistant", "content": result.text})
        return parse_sql_response(result.text)

    def draft(self) -> SqlDraft:
        return self._ask()

    def repair(self, error: str) -> SqlDraft:
        self.messages.append({"role": "user", "content": SQL_RETRY_USER.format(error=error)})
        return self._ask()
