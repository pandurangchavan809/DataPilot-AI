"""Signup, login, token refresh, logout and the current user."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..core.errors import AuthError
from ..services import services
from .deps import parse_body, require_auth
from .schemas import AuthRequest, RefreshRequest

bp = Blueprint("auth", __name__)


@bp.post("/signup")
def signup():
    body = parse_body(AuthRequest)
    auth = services().auth
    user = auth.signup(body.email, body.password)
    user = auth.login(body.email, body.password, ip=request.remote_addr, user_agent=request.user_agent.string)
    return jsonify(auth.issue_tokens(user)), 201


@bp.post("/login")
def login():
    body = parse_body(AuthRequest)
    auth = services().auth
    user = auth.login(body.email, body.password, ip=request.remote_addr, user_agent=request.user_agent.string)
    return jsonify(auth.issue_tokens(user))


@bp.post("/refresh")
def refresh():
    body = parse_body(RefreshRequest)
    return jsonify(services().auth.refresh(body.refresh_token))


@bp.post("/logout")
def logout():
    body = parse_body(RefreshRequest)
    services().auth.logout(body.refresh_token)
    return "", 204


@bp.get("/me")
def me():
    require_auth()
    user = services().auth.store.get_by_id(g.user_id)
    if user is None:
        raise AuthError("Account no longer exists.", code="invalid_token")
    return jsonify(user=user.public_dict())
