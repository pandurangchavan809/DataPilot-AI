"""Signup, login, JWT access/refresh tokens and logout.

Access token:  short-lived (15 min), sent as "Authorization: Bearer <token>" on every API call.
               Stateless: verified by signature only, never looked up in the database.
Refresh token: long-lived (7 days), used only on /api/auth/refresh to get a new pair.
               Stored by its id (jti) so it can be revoked. Each one works once (rotation);
               presenting a used one again means it was stolen, so all the user's
               sessions are logged out.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

import jwt
from werkzeug.security import check_password_hash, generate_password_hash

from ..config import Settings
from ..core.errors import AuthError, ConflictError, ValidationError
from .store import User, UserStore

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Checked against when the email doesn't exist, so a wrong email takes as long as a wrong password.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def check_password_strength(password: str) -> None:
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters.")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValidationError("Password must contain a letter and a number.")
    if len(password) > 128:
        raise ValidationError("Password is too long.")


class AuthService:
    def __init__(self, settings: Settings, store: UserStore):
        self._settings = settings
        self.store = store

    def seed_demo_user(self) -> None:
        email, password = self._settings.demo_user_email.strip().lower(), self._settings.demo_user_password
        if email and password and not self.store.get_by_email(email):
            self.store.create(email, generate_password_hash(password))
            logger.info("Created demo user '%s'", email)

    # --- account actions -----------------------------------------------------

    def signup(self, email: str, password: str) -> User:
        email = email.strip().lower()
        if not EMAIL.match(email) or len(email) > 254:
            raise ValidationError("Enter a valid email address.")
        check_password_strength(password)
        user = self.store.create(email, generate_password_hash(password))
        if user is None:
            raise ConflictError("An account with this email already exists.")
        return user

    def login(self, email: str, password: str, *, ip: str | None, user_agent: str | None) -> User:
        email = email.strip().lower()
        user = self.store.get_by_email(email)
        valid = check_password_hash(user.password_hash if user else _DUMMY_HASH, password)
        self.store.record_login(email, user if valid else None, ip=ip, user_agent=user_agent)
        if not (user and valid):
            raise AuthError("Incorrect email or password.", code="invalid_credentials")
        return self.store.get_by_id(user.id) or user

    def logout(self, refresh_token: str) -> None:
        try:
            claims = self._decode(refresh_token, "refresh")
        except AuthError:
            return  # already invalid: nothing to revoke
        self.store.use_refresh_token(claims["jti"])

    # --- tokens --------------------------------------------------------------

    def issue_tokens(self, user: User) -> dict:
        now = int(time.time())
        access_exp = now + self._settings.access_token_minutes * 60
        refresh_exp = now + self._settings.refresh_token_days * 86400
        refresh_jti = uuid.uuid4().hex
        self.store.add_refresh_token(refresh_jti, user.id, refresh_exp)
        return {
            "access_token": self._encode(user, "access", uuid.uuid4().hex, now, access_exp),
            "refresh_token": self._encode(user, "refresh", refresh_jti, now, refresh_exp),
            "token_type": "Bearer",
            "expires_in": access_exp - now,
            "user": user.public_dict(),
        }

    def refresh(self, refresh_token: str) -> dict:
        claims = self._decode(refresh_token, "refresh")
        status = self.store.use_refresh_token(claims["jti"])
        if status == "reused":
            # A rotated token came back: someone else has a copy. Log out everywhere.
            self.store.revoke_all_refresh_tokens(int(claims["sub"]))
            logger.warning("Refresh token reuse detected for user %s", claims["sub"])
        if status != "ok":
            raise AuthError("Session expired. Please log in again.", code="invalid_token")
        user = self.store.get_by_id(int(claims["sub"]))
        if user is None:
            raise AuthError("Account no longer exists.", code="invalid_token")
        return self.issue_tokens(user)

    def user_from_access_token(self, token: str) -> dict:
        """Verify an access token; returns its claims (no database lookup)."""
        return self._decode(token, "access")

    def _encode(self, user: User, kind: str, jti: str, iat: int, exp: int) -> str:
        payload = {"sub": str(user.id), "email": user.email, "type": kind, "jti": jti, "iat": iat, "exp": exp}
        return jwt.encode(payload, self._settings.jwt_secret, algorithm=ALGORITHM)

    def _decode(self, token: str, kind: str) -> dict:
        try:
            claims = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=[ALGORITHM],  # pinned: never trust the token's own "alg" header
                options={"require": ["sub", "type", "jti", "exp"]},
            )
        except jwt.ExpiredSignatureError:
            raise AuthError("Session expired.", code="token_expired") from None
        except jwt.InvalidTokenError:
            raise AuthError("Invalid token.", code="invalid_token") from None
        if claims.get("type") != kind:
            raise AuthError("Wrong token type.", code="invalid_token")
        return claims
