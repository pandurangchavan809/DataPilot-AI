"""User store: a small SQLite file (auth/auth.db), separate from the demo data.

Tables:
  users           one row per account (password stored only as a salted hash)
  refresh_tokens  one row per issued refresh token, so tokens can be revoked
  login_events    every login attempt (who, when, from which IP), for tracking
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    INTEGER NOT NULL,
    last_login_at INTEGER,
    login_count   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS refresh_tokens (
    jti        TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL,
    revoked    INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS login_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    email      TEXT NOT NULL,
    success    INTEGER NOT NULL,
    ip         TEXT,
    user_agent TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_refresh_user ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_login_user ON login_events(user_id);
"""


@dataclass(frozen=True)
class User:
    id: int
    email: str
    password_hash: str
    created_at: int
    last_login_at: int | None
    login_count: int

    def public_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "created_at": self.created_at,
            "last_login_at": self.last_login_at,
            "login_count": self.login_count,
        }


class UserStore:
    def __init__(self, path: Path):
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        # One short-lived connection per operation: safe across server threads.
        db = sqlite3.connect(self._path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    # --- users ---------------------------------------------------------------

    def get_by_email(self, email: str) -> User | None:
        with self._conn() as db:
            row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return User(**row) if row else None

    def get_by_id(self, user_id: int) -> User | None:
        with self._conn() as db:
            row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return User(**row) if row else None

    def create(self, email: str, password_hash: str) -> User | None:
        """Insert a user; returns None if the email is already taken."""
        try:
            with self._conn() as db:
                cur = db.execute(
                    "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                    (email, password_hash, int(time.time())),
                )
                user_id = cur.lastrowid
        except sqlite3.IntegrityError:
            return None
        return self.get_by_id(user_id)

    def record_login(self, email: str, user: User | None, *, ip: str | None, user_agent: str | None) -> None:
        now = int(time.time())
        with self._conn() as db:
            db.execute(
                "INSERT INTO login_events (user_id, email, success, ip, user_agent, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user.id if user else None, email, int(user is not None), ip, (user_agent or "")[:300], now),
            )
            if user:
                db.execute(
                    "UPDATE users SET last_login_at = ?, login_count = login_count + 1 WHERE id = ?",
                    (now, user.id),
                )

    # --- refresh tokens ------------------------------------------------------

    def add_refresh_token(self, jti: str, user_id: int, expires_at: int) -> None:
        with self._conn() as db:
            db.execute(
                "INSERT INTO refresh_tokens (jti, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (jti, user_id, expires_at, int(time.time())),
            )

    def use_refresh_token(self, jti: str) -> str:
        """Revoke a refresh token so it can be used only once.

        Returns "ok" (was valid, now revoked), "reused" (already revoked) or "unknown".
        """
        with self._conn() as db:
            # Atomic check-and-revoke: two parallel refreshes can't both succeed.
            if db.execute("UPDATE refresh_tokens SET revoked = 1 WHERE jti = ? AND revoked = 0", (jti,)).rowcount:
                return "ok"
            exists = db.execute("SELECT 1 FROM refresh_tokens WHERE jti = ?", (jti,)).fetchone()
            return "reused" if exists else "unknown"

    def revoke_all_refresh_tokens(self, user_id: int) -> None:
        with self._conn() as db:
            db.execute("UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM refresh_tokens WHERE expires_at < ?", (int(time.time()),))
