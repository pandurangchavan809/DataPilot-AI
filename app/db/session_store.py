"""Ephemeral session storage for connection configs.

Credentials are Fernet-encrypted before storage and expire with the session
TTL. The in-memory backend suits a single process. Use Redis when running
multiple gunicorn workers or replicas.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken

from ..config import Settings


class SessionStore(Protocol):
    def get(self, sid: str) -> dict | None: ...
    def set(self, sid: str, data: dict) -> None: ...
    def delete(self, sid: str) -> None: ...


class MemorySessionStore:
    def __init__(self, ttl_seconds: int):
        self._ttl = ttl_seconds
        self._data: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def _purge(self) -> None:
        now = time.monotonic()
        for sid in [k for k, (exp, _) in self._data.items() if exp < now]:
            del self._data[sid]

    def get(self, sid: str) -> dict | None:
        with self._lock:
            self._purge()
            item = self._data.get(sid)
            if not item:
                return None
            self._data[sid] = (time.monotonic() + self._ttl, item[1])  # sliding expiry
            return json.loads(item[1])

    def set(self, sid: str, data: dict) -> None:
        with self._lock:
            self._data[sid] = (time.monotonic() + self._ttl, json.dumps(data))

    def delete(self, sid: str) -> None:
        with self._lock:
            self._data.pop(sid, None)


class RedisSessionStore:
    PREFIX = "datapilot:session:"

    def __init__(self, url: str, ttl_seconds: int):
        import redis

        self._redis = redis.Redis.from_url(url, decode_responses=True)
        self._ttl = ttl_seconds

    def get(self, sid: str) -> dict | None:
        key = self.PREFIX + sid
        raw = self._redis.get(key)
        if raw is None:
            return None
        self._redis.expire(key, self._ttl)
        return json.loads(raw)

    def set(self, sid: str, data: dict) -> None:
        self._redis.setex(self.PREFIX + sid, self._ttl, json.dumps(data))

    def delete(self, sid: str) -> None:
        self._redis.delete(self.PREFIX + sid)


class SecretBox:
    def __init__(self, secret_key: str):
        key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest())
        self._fernet = Fernet(key)

    def seal(self, payload: dict) -> str:
        return self._fernet.encrypt(json.dumps(payload).encode()).decode()

    def open(self, token: str) -> dict | None:
        try:
            return json.loads(self._fernet.decrypt(token.encode()))
        except (InvalidToken, ValueError):
            return None


def build_session_store(settings: Settings) -> SessionStore:
    ttl = settings.session_ttl_minutes * 60
    if settings.session_backend == "redis":
        return RedisSessionStore(settings.redis_url, ttl)
    return MemorySessionStore(ttl)
