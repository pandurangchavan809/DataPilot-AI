from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine


def build_connection_url(connection_type: str, payload: dict) -> str:
    if connection_type == "sqlite":
        db_path = payload.get("path", "./data/top50_countries.db")
        return f"sqlite:///{db_path}"

    if connection_type == "mysql":
        user = payload["user"]
        password = payload["password"]
        host = payload.get("host", "localhost")
        port = payload.get("port", 3306)
        database = payload["database"]
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"

    raise ValueError("Unsupported database type")


def get_engine(connection_url: str, echo: bool = False) -> Engine:
    return create_engine(connection_url, future=True, echo=echo)


def inspect_schema(engine: Engine) -> dict:
    inspector = inspect(engine)
    schema = {}
    for table_name in inspector.get_table_names():
        columns = inspector.get_columns(table_name)
        schema[table_name] = [
            {"name": column["name"], "type": str(column["type"])} for column in columns
        ]
    return schema


def execute_sql(engine: Engine, sql: str, limit: int = 500) -> dict:
    with engine.connect() as connection:
        result = connection.execute(text(sql))
        if result.returns_rows:
            rows = [dict(row) for row in result.fetchmany(limit)]
            columns = result.keys()
            return {"columns": list(columns), "rows": rows}
        return {"rows_affected": result.rowcount}
