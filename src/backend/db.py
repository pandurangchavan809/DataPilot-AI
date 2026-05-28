from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine


def build_connection_url(connection_type: str, payload: dict) -> str:
    """Build database connection URL from connection type and payload."""
    if connection_type == "sqlite":
        db_path = payload.get("path", "./data/top50_countries.db")
        return f"sqlite:///{db_path}"

    if connection_type == "mysql":
        user = payload.get("user")
        password = payload.get("password")
        host = payload.get("host", "localhost")
        port = payload.get("port", 3306)
        database = payload.get("database")
        
        if not all([user, password, database]):
            raise ValueError("MySQL requires user, password, and database")
        
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"

    raise ValueError(f"Unsupported database type: {connection_type}")


def get_engine(connection_url: str, echo: bool = False) -> Engine:
    """Create and return SQLAlchemy engine."""
    try:
        return create_engine(connection_url, future=True, echo=echo)
    except Exception as exc:
        raise RuntimeError(f"Failed to create database engine: {str(exc)}")


def inspect_schema(engine: Engine) -> dict:
    """Inspect and return database schema."""
    try:
        inspector = inspect(engine)
        schema = {}
        for table_name in inspector.get_table_names():
            columns = inspector.get_columns(table_name)
            schema[table_name] = [
                {"name": column["name"], "type": str(column["type"])} for column in columns
            ]
        return schema
    except Exception as exc:
        raise RuntimeError(f"Failed to inspect schema: {str(exc)}")


def execute_sql(engine, sql: str, limit: int = 500) -> dict:
    """
    Execute SQL query and return results.
    """

    try:
        with engine.connect() as connection:

            result = connection.execute(text(sql))

            if result.returns_rows:

                rows = [
                    dict(row._mapping)
                    for row in result.fetchmany(limit)
                ]

                columns = list(result.keys())

                return {
                    "columns": columns,
                    "rows": rows
                }

            return {
                "rows_affected": result.rowcount
            }

    except Exception as exc:
        raise RuntimeError(
            f"Query execution failed: {str(exc)}"
        )
