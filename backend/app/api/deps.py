"""Request helpers shared by blueprints."""

from __future__ import annotations

import re
from typing import TypeVar

from flask import request
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from ..core.errors import ValidationError

T = TypeVar("T", bound=BaseModel)

SESSION_HEADER = "X-Session-Id"
SESSION_ID = re.compile(r"^[A-Za-z0-9-]{16,64}$")


def session_id() -> str:
    sid = request.headers.get(SESSION_HEADER, "")
    if not SESSION_ID.match(sid):
        raise ValidationError(f"Missing or invalid {SESSION_HEADER} header.")
    return sid


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
