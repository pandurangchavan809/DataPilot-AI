"""Signup, login, token refresh, logout and the current user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..core.errors import AuthError
from ..services import Services, get_services
from .deps import client_ip, rate_limited, require_auth
from .schemas import AuthRequest, RefreshRequest

router = APIRouter(tags=["auth"], dependencies=[Depends(rate_limited("auth_rate_limit"))])


def _login(body: AuthRequest, request: Request, svc: Services) -> dict:
    user = svc.auth.login(
        body.email,
        body.password,
        ip=client_ip(request, svc.settings.proxy_fix_hops),
        user_agent=request.headers.get("user-agent"),
    )
    return svc.auth.issue_tokens(user)


@router.post("/signup", status_code=201)
def signup(body: AuthRequest, request: Request, svc: Services = Depends(get_services)):
    svc.auth.signup(body.email, body.password)
    return _login(body, request, svc)


@router.post("/login")
def login(body: AuthRequest, request: Request, svc: Services = Depends(get_services)):
    return _login(body, request, svc)


@router.post("/refresh")
def refresh(body: RefreshRequest, svc: Services = Depends(get_services)):
    return svc.auth.refresh(body.refresh_token)


@router.post("/logout", status_code=204)
def logout(body: RefreshRequest, svc: Services = Depends(get_services)) -> None:
    svc.auth.logout(body.refresh_token)


@router.get("/me")
def me(claims: dict = Depends(require_auth), svc: Services = Depends(get_services)):
    user = svc.auth.store.get_by_id(int(claims["sub"]))
    if user is None:
        raise AuthError("Account no longer exists.", code="invalid_token")
    return {"user": user.public_dict()}
