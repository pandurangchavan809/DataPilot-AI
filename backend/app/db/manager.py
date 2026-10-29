"""Per-session connection lifecycle.

The session store is the source of truth (shareable across workers). Engines
and introspected schemas are per-process caches rebuilt on demand.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from sqlalchemy.engine import Engine

from ..config import Settings
from ..core.errors import NotConnectedError
from .connectors import ConnectionConfig, create_readonly_engine, verify_connection
from .introspect import SchemaInfo, introspect_schema
from .session_store import SecretBox, SessionStore

logger = logging.getLogger(__name__)


@dataclass
class ActiveConnection:
    config: ConnectionConfig
    engine: Engine
    schema: SchemaInfo
    connected_at: float


class ConnectionManager:
    def __init__(self, settings: Settings, store: SessionStore):
        self._settings = settings
        self._store = store
        self._box = SecretBox(settings.secret_key)
        self._cache: OrderedDict[str, ActiveConnection] = OrderedDict()
        self._lock = threading.Lock()

    def connect(self, sid: str, config: ConnectionConfig) -> ActiveConnection:
        engine = create_readonly_engine(config, self._settings)
        verify_connection(engine)
        schema = introspect_schema(engine, config.dialect)
        active = ActiveConnection(config, engine, schema, time.time())
        self._store.set(sid, {"config": self._box.seal(config.model_dump()), "connected_at": active.connected_at})
        self._remember(sid, active)
        logger.info("Session connected to %s", config.type, extra={"session": sid[:8]})
        return active

    def get(self, sid: str) -> ActiveConnection:
        record = self._store.get(sid)
        if not record:
            self._forget(sid)
            raise NotConnectedError()
        with self._lock:
            cached = self._cache.get(sid)
            if cached and cached.connected_at == record["connected_at"]:
                self._cache.move_to_end(sid)
                return cached
        payload = self._box.open(record["config"])
        if payload is None:
            self._store.delete(sid)
            raise NotConnectedError("Session expired. Please reconnect.")
        config = ConnectionConfig(**payload)
        engine = create_readonly_engine(config, self._settings)
        active = ActiveConnection(config, engine, introspect_schema(engine, config.dialect), record["connected_at"])
        self._remember(sid, active)
        return active

    def peek(self, sid: str) -> ActiveConnection | None:
        try:
            return self.get(sid)
        except NotConnectedError:
            return None

    def refresh_schema(self, sid: str) -> ActiveConnection:
        active = self.get(sid)
        active.schema = introspect_schema(active.engine, active.config.dialect)
        return active

    def disconnect(self, sid: str) -> None:
        self._store.delete(sid)
        self._forget(sid)

    def _remember(self, sid: str, active: ActiveConnection) -> None:
        with self._lock:
            old = self._cache.pop(sid, None)
            if old and old.engine is not active.engine:
                old.engine.dispose()
            self._cache[sid] = active
            while len(self._cache) > self._settings.engine_cache_size:
                _, evicted = self._cache.popitem(last=False)
                evicted.engine.dispose()

    def _forget(self, sid: str) -> None:
        with self._lock:
            old = self._cache.pop(sid, None)
        if old:
            old.engine.dispose()
