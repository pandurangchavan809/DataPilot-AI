"""Schema introspection and prompt rendering."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from .executor import execute_readonly

logger = logging.getLogger(__name__)

MAX_TABLES = 300


@dataclass
class Column:
    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False


@dataclass
class ForeignKey:
    columns: list[str]
    ref_table: str
    ref_columns: list[str]


@dataclass
class Table:
    name: str
    columns: list[Column]
    foreign_keys: list[ForeignKey] = field(default_factory=list)
    is_view: bool = False
    samples: list[list] | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "is_view": self.is_view,
            "columns": [vars(c) for c in self.columns],
            "foreign_keys": [vars(fk) for fk in self.foreign_keys],
        }


@dataclass
class SchemaInfo:
    dialect: str
    tables: list[Table]

    def table(self, name: str) -> Table | None:
        lowered = name.lower()
        return next((t for t in self.tables if t.name.lower() == lowered), None)

    def to_dict(self) -> dict:
        return {"dialect": self.dialect, "tables": [t.to_dict() for t in self.tables]}


def introspect_schema(engine: Engine, dialect: str) -> SchemaInfo:
    inspector = inspect(engine)
    names = [(n, False) for n in inspector.get_table_names()]
    names += [(n, True) for n in inspector.get_view_names()]
    tables: list[Table] = []
    for name, is_view in names[:MAX_TABLES]:
        try:
            pk = set((inspector.get_pk_constraint(name) or {}).get("constrained_columns") or [])
            columns = [
                Column(c["name"], str(c["type"]), bool(c.get("nullable", True)), c["name"] in pk)
                for c in inspector.get_columns(name)
            ]
            fks = [
                ForeignKey(fk["constrained_columns"], fk["referred_table"], fk["referred_columns"])
                for fk in inspector.get_foreign_keys(name)
                if fk.get("referred_table")
            ]
            tables.append(Table(name, columns, fks, is_view))
        except Exception as exc:  # noqa: BLE001 - skip tables we cannot read
            logger.warning("Skipping table %s during introspection: %s", name, exc)
    return SchemaInfo(dialect, tables)


def load_samples(engine: Engine, table: Table, limit: int, timeout_seconds: int) -> None:
    if table.samples is not None or limit <= 0:
        return
    quote = engine.dialect.identifier_preparer.quote
    try:
        result = execute_readonly(
            engine, f"SELECT * FROM {quote(table.name)} LIMIT {int(limit)}",
            row_limit=limit, timeout_seconds=timeout_seconds,
        )
        table.samples = result.rows
    except Exception as exc:  # noqa: BLE001
        logger.info("Could not sample %s: %s", table.name, exc)
        table.samples = []


def render_tables(tables: list[Table]) -> str:
    """Compact DDL-like rendering, including sample rows, for prompts."""
    blocks = []
    for t in tables:
        cols = []
        for c in t.columns:
            flags = " PRIMARY KEY" if c.primary_key else ""
            cols.append(f"  {c.name} {c.type}{flags}")
        for fk in t.foreign_keys:
            cols.append(
                f"  FOREIGN KEY ({', '.join(fk.columns)}) REFERENCES {fk.ref_table}({', '.join(fk.ref_columns)})"
            )
        kind = "VIEW" if t.is_view else "TABLE"
        block = f"{kind} {t.name} (\n" + ",\n".join(cols) + "\n)"
        if t.samples:
            header = " | ".join(c.name for c in t.columns)
            rows = "\n".join(" | ".join(_short(v) for v in row) for row in t.samples)
            block += f"\n-- sample rows:\n-- {header}\n" + "\n".join(f"-- {line}" for line in rows.splitlines())
        blocks.append(block)
    return "\n\n".join(blocks)


def render_table_index(tables: list[Table]) -> str:
    return "\n".join(f"- {t.name}: {', '.join(c.name for c in t.columns)}" for t in tables)


def _short(value) -> str:
    text = "NULL" if value is None else str(value)
    return text if len(text) <= 40 else text[:37] + "..."
