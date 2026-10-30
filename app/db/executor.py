"""Executes guarded SQL inside an always-rolled-back transaction."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from sqlalchemy.engine import Engine

from ..core.errors import QueryExecutionError
from ..core.serialization import to_jsonable


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool
    elapsed_ms: int
    column_types: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "columns": self.columns,
            "column_types": self.column_types,
            "rows": self.rows,
            "row_count": self.row_count,
            "truncated": self.truncated,
            "elapsed_ms": self.elapsed_ms,
        }


def _infer_type(values: list) -> str:
    sample = [v for v in values if v is not None][:50]
    if not sample:
        return "unknown"
    if all(isinstance(v, bool) for v in sample):
        return "boolean"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in sample):
        return "number"
    return "string"


def execute_readonly(engine: Engine, sql: str, *, row_limit: int, timeout_seconds: int) -> QueryResult:
    started = time.perf_counter()
    try:
        with engine.connect() as conn:
            raw = conn.connection.driver_connection
            is_sqlite = engine.dialect.name == "sqlite"
            if is_sqlite:
                deadline = time.monotonic() + timeout_seconds
                raw.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
            trans = conn.begin()
            try:
                result = conn.execution_options(no_parameters=True).exec_driver_sql(sql)
                if not result.returns_rows:
                    raise QueryExecutionError("Statement did not return rows.")
                columns = list(result.keys())
                fetched = result.fetchmany(row_limit + 1)
            finally:
                trans.rollback()
                if is_sqlite:
                    raw.set_progress_handler(None, 0)
    except QueryExecutionError:
        raise
    except Exception as exc:  # noqa: BLE001
        message = str(getattr(exc, "orig", None) or exc).splitlines()[0][:500]
        if "interrupted" in message.lower():
            message = f"Query exceeded the {timeout_seconds}s time limit."
        raise QueryExecutionError(message) from exc

    truncated = len(fetched) > row_limit
    rows = [[to_jsonable(v) for v in row] for row in fetched[:row_limit]]
    column_types = [_infer_type([r[i] for r in rows]) for i in range(len(columns))]
    return QueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        column_types=column_types,
    )
