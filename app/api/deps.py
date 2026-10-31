"""Request dependencies shared by routers."""

from __future__ import annotations

import re

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..core.errors import AuthError, RateLimitError, ValidationError
from ..services import Services, get_services

SESSION_HEADER = "X-Session-Id"
SESSION_ID = re.compile(r"^[A-Za-z0-9-]{16,64}$")

# auto_error=False so a missing token gets our own 401 format. Also adds "Authorize" to /api/docs.
bearer = HTTPBearer(auto_error=False)


def client_ip(request: Request, proxy_hops: int) -> str:
    """The real client IP. Behind N proxies it's the Nth address from the right, the last one a proxy
    we trust added. Addresses further left are sent by the client and could be faked."""
    forwarded = [ip.strip() for ip in request.headers.get("x-forwarded-for", "").split(",") if ip.strip()]
    if proxy_hops and len(forwarded) >= proxy_hops:
        return forwarded[-proxy_hops]
    return request.client.host if request.client else "unknown"


def rate_limited(setting: str):
    """Dependency that applies the limit named by a settings field, such as "rate_limit"."""

    def check(request: Request, svc: Services = Depends(get_services)) -> None:
        ip = client_ip(request, svc.settings.proxy_fix_hops)
        if not svc.limiter.allow(getattr(svc.settings, setting), setting, ip):
            raise RateLimitError()

    return check


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    svc: Services = Depends(get_services),
) -> dict:
    """Needs a valid access token. Returns its claims."""
    if credentials is None:
        raise AuthError("Please log in.")
    return svc.auth.user_from_access_token(credentials.credentials)


def session_id(
    claims: dict = Depends(require_auth),
    sid: str = Header(default="", alias=SESSION_HEADER),
) -> str:
    if not SESSION_ID.match(sid):
        raise ValidationError(f"Missing or invalid {SESSION_HEADER} header.")
    # Scope the DB session to the logged-in user, so one user can never reach another's connection.
    return f"u{claims['sub']}-{sid}"
