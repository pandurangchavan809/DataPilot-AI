"""Deterministic read-only SQL guard.

LLM output is untrusted input. Before anything reaches a database it must
parse as exactly one read-only query, contain no write/DDL/admin nodes or
dangerous functions, and carry a row limit.
"""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from ..core.errors import UnsafeQueryError

_FORBIDDEN_NODE_NAMES = (
    "Insert", "Update", "Delete", "Merge", "Drop", "Create", "Alter", "AlterTable",
    "TruncateTable", "Command", "Into", "Lock", "Grant", "Revoke", "Copy", "LoadData",
    "Pragma", "Set", "Use", "Transaction", "Commit", "Rollback", "Attach", "Detach",
)
FORBIDDEN_NODES = tuple(t for t in (getattr(exp, n, None) for n in _FORBIDDEN_NODE_NAMES) if t)

FORBIDDEN_FUNCTIONS = {
    # PostgreSQL
    "pg_sleep", "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_stat_file",
    "lo_import", "lo_export", "dblink", "dblink_exec", "pg_terminate_backend",
    "pg_cancel_backend", "set_config", "pg_reload_conf", "query_to_xml",
    # MySQL
    "sleep", "benchmark", "load_file", "get_lock", "release_lock",
    # SQLite
    "load_extension", "readfile", "writefile", "edit", "fts3_tokenizer",
}

FORBIDDEN_KEYWORDS = re.compile(
    r"\b(ATTACH|DETACH|PRAGMA|VACUUM|REINDEX|COPY|CALL|EXEC|EXECUTE|GRANT|REVOKE|"
    r"OUTFILE|DUMPFILE|HANDLER|SHUTDOWN|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|"
    r"TRUNCATE|REPLACE\s+INTO|MERGE|RENAME)\b",
    re.IGNORECASE,
)
STRING_LITERAL = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|`[^`]*`")
COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)


def _function_name(node: exp.Func) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.name).lower()
    return node.sql_name().lower()


def validate_readonly_sql(sql: str, dialect: str, row_limit: int) -> str:
    """Return a normalised, limited, read-only version of ``sql`` or raise."""
    if not sql or not sql.strip():
        raise UnsafeQueryError("Empty SQL statement.")

    stripped = COMMENTS.sub(" ", sql).strip().rstrip(";").strip()
    keyword_hit = FORBIDDEN_KEYWORDS.search(STRING_LITERAL.sub("''", stripped))
    if keyword_hit:
        raise UnsafeQueryError(
            f"Blocked keyword '{keyword_hit.group(1).upper()}'. Only read-only queries are allowed."
        )

    try:
        statements = [s for s in sqlglot.parse(stripped, read=dialect) if s is not None]
    except ParseError as exc:
        raise UnsafeQueryError(f"SQL could not be parsed: {str(exc).splitlines()[0]}") from exc

    if len(statements) != 1:
        raise UnsafeQueryError("Exactly one SQL statement is allowed.")
    statement = statements[0]

    if not isinstance(statement, exp.Query):
        raise UnsafeQueryError("Only SELECT queries are allowed.")

    for node in statement.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise UnsafeQueryError(f"Blocked operation: {type(node).__name__}.")
        if isinstance(node, exp.Func) and _function_name(node) in FORBIDDEN_FUNCTIONS:
            raise UnsafeQueryError(f"Blocked function: {_function_name(node)}().")

    if statement.args.get("limit") is None:
        statement = statement.limit(row_limit)

    return statement.sql(dialect=dialect)
