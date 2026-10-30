"""Connection lifecycle and schema endpoints."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..services import services
from .deps import parse_body, session_id
from .schemas import ConnectRequest

bp = Blueprint("connections", __name__)


def _payload(active) -> dict:
    return {"connection": active.config.public_dict(), "schema": active.schema.to_dict()}


@bp.post("/connections")
def connect():
    config = parse_body(ConnectRequest)
    active = services().connections.connect(session_id(), config)
    return jsonify(_payload(active)), 201


@bp.get("/connections/current")
def current():
    active = services().connections.peek(session_id())
    return jsonify(_payload(active) if active else {"connection": None, "schema": None})


@bp.delete("/connections/current")
def disconnect():
    services().connections.disconnect(session_id())
    return "", 204


@bp.post("/schema/refresh")
def refresh_schema():
    active = services().connections.refresh_schema(session_id())
    return jsonify(_payload(active))
