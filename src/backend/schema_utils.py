from __future__ import annotations

from sqlalchemy.engine import Engine

from .db import inspect_schema


def format_schema(schema: dict) -> list[dict]:
    return [
        {
            "table": table,
            "columns": [column["name"] for column in columns],
            "details": columns,
        }
        for table, columns in schema.items()
    ]


def build_schema_prompt(schema: dict) -> str:
    formatted = []
    for table, columns in schema.items():
        column_list = ", ".join([column["name"] + " (" + column["type"] + ")" for column in columns])
        formatted.append(f"Table {table}: {column_list}")

    return "\n".join(formatted)
