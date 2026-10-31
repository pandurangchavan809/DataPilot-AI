"""Connection lifecycle and schema endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..services import Services, get_services
from .deps import rate_limited, session_id
from .schemas import ConnectRequest

router = APIRouter(tags=["connections"], dependencies=[Depends(rate_limited("rate_limit"))])


def _payload(active) -> dict:
    return {"connection": active.config.public_dict(), "schema": active.schema.to_dict()}


@router.post("/connections", status_code=201)
def connect(config: ConnectRequest, sid: str = Depends(session_id), svc: Services = Depends(get_services)):
    return _payload(svc.connections.connect(sid, config))


@router.get("/connections/current")
def current(sid: str = Depends(session_id), svc: Services = Depends(get_services)):
    active = svc.connections.peek(sid)
    return _payload(active) if active else {"connection": None, "schema": None}


@router.delete("/connections/current", status_code=204)
def disconnect(sid: str = Depends(session_id), svc: Services = Depends(get_services)) -> None:
    svc.connections.disconnect(sid)


@router.post("/schema/refresh")
def refresh_schema(sid: str = Depends(session_id), svc: Services = Depends(get_services)):
    return _payload(svc.connections.refresh_schema(sid))
