"""Request helpers shared by blueprints."""

from __future__ import annotations

import re
from typing import TypeVar

from flask import g, request
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from ..core.errors import AuthError, ValidationError
from ..services import services

T = TypeVar("T", bound=BaseModel)

SESSION_HEADER = "X-Session-Id"
SESSION_ID = re.compile(r"^[A-Za-z0-9-]{16,64}$")


def require_auth() -> None:
    """before_request hook for protected blueprints: needs a valid access token."""
    if request.method == "OPTIONS":
        return  # CORS preflight carries no token
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("Please log in.")
    claims = services().auth.user_from_access_token(token)
    g.user_id = int(claims["sub"])
    g.user_email = claims["email"]


def session_id() -> str:
    sid = request.headers.get(SESSION_HEADER, "")
    if not SESSION_ID.match(sid):
        raise ValidationError(f"Missing or invalid {SESSION_HEADER} header.")
    # Scope the DB session to the logged-in user, so one user can never reach another's connection.
    return f"u{g.user_id}-{sid}"


def parse_body(model: type[T]) -> T:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object.")
    try:
        return model.model_validate(payload)
    except PydanticValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(p) for p in first.get("loc", ()))
        raise ValidationError(f"{location}: {first.get('msg')}" if location else first.get("msg", "Invalid input"))
