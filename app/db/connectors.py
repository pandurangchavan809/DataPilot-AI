"""Database connection configs and read-only engine factories.

Read-only is enforced at the driver/session level here, in addition to the
SQL guard. Even if a write statement slipped past the guard, the database
itself would reject it.
"""

from __future__ import annotations

import sqlite3
import ssl
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import URL, create_engine, event, text
from sqlalchemy.engine import Engine

from ..config import Settings
from ..core.errors import ConnectionFailedError, ValidationError

DbType = Literal["sqlite_demo", "postgresql", "mysql"]

DIALECTS: dict[str, str] = {"sqlite_demo": "sqlite", "postgresql": "postgres", "mysql": "mysql"}
DEFAULT_PORTS = {"postgresql": 5432, "mysql": 3306}


class ConnectionConfig(BaseModel):
    type: DbType
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=1024)
    ssl: bool = False

    @property
    def dialect(self) -> str:
        return DIALECTS[self.type]

    def validate_required(self) -> None:
        if self.type == "sqlite_demo":
            return
        missing = [f for f in ("host", "database", "username") if not getattr(self, f)]
        if missing:
            raise ValidationError(f"Missing required fields: {', '.join(missing)}")

    def display_name(self) -> str:
        if self.type == "sqlite_demo":
            return "Demo · World Countries"
        return f"{self.database} @ {self.host}"

    def public_dict(self) -> dict:
        return {
            "type": self.type,
            "dialect": self.dialect,
            "name": self.display_name(),
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "username": self.username,
            "ssl": self.ssl,
        }


def _sqlite_readonly_engine(path: Path) -> Engine:
    if not path.exists():
        raise ConnectionFailedError("Demo database is not initialised.")
    uri = f"{path.resolve().as_uri()}?mode=ro"

    def creator():
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        conn.execute("PRAGMA query_only = ON")
        return conn

    return create_engine("sqlite://", creator=creator, pool_pre_ping=True)


def _postgres_engine(cfg: ConnectionConfig, settings: Settings) -> Engine:
    url = URL.create(
        "postgresql+psycopg",
        username=cfg.username,
        password=cfg.password,
        host=cfg.host,
        port=cfg.port or DEFAULT_PORTS["postgresql"],
        database=cfg.database,
    )
    timeout_ms = settings.query_timeout_seconds * 1000
    connect_args = {
        "connect_timeout": 10,
        "options": f"-c default_transaction_read_only=on -c statement_timeout={timeout_ms}",
        "sslmode": "require" if cfg.ssl else "prefer",
    }
    return create_engine(
        url, connect_args=connect_args, pool_size=2, max_overflow=3, pool_pre_ping=True, pool_recycle=1800
    )


def _mysql_engine(cfg: ConnectionConfig, settings: Settings) -> Engine:
    url = URL.create(
        "mysql+pymysql",
        username=cfg.username,
        password=cfg.password,
        host=cfg.host,
        port=cfg.port or DEFAULT_PORTS["mysql"],
        database=cfg.database,
    )
    connect_args: dict = {"connect_timeout": 10, "read_timeout": settings.query_timeout_seconds + 5}
    if cfg.ssl:
        connect_args["ssl"] = ssl.create_default_context()
    engine = create_engine(
        url, connect_args=connect_args, pool_size=2, max_overflow=3, pool_pre_ping=True, pool_recycle=1800
    )
    timeout_ms = settings.query_timeout_seconds * 1000

    @event.listens_for(engine, "connect")
    def _readonly_session(dbapi_conn, _record):
        with dbapi_conn.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION READ ONLY")
            cur.execute(f"SET SESSION max_execution_time = {int(timeout_ms)}")

    return engine


def create_readonly_engine(cfg: ConnectionConfig, settings: Settings) -> Engine:
    if cfg.type not in settings.allowed_db_types:
        raise ValidationError(f"Database type '{cfg.type}' is not enabled.")
    cfg.validate_required()
    if cfg.type == "sqlite_demo":
        return _sqlite_readonly_engine(settings.demo_db_path)
    if cfg.type == "postgresql":
        return _postgres_engine(cfg, settings)
    return _mysql_engine(cfg, settings)


def verify_connection(engine: Engine) -> None:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        engine.dispose()
        raise ConnectionFailedError(f"Could not connect: {_short_error(exc)}") from exc


def _short_error(exc: Exception) -> str:
    message = str(getattr(exc, "orig", None) or exc)
    return message.splitlines()[0][:300]
