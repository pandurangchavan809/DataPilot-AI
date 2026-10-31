"""Health and client bootstrap configuration."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..llm.registry import PROVIDER_LABELS
from ..services import Services, get_services
from .deps import require_auth

router = APIRouter(tags=["meta"])  # public
private_router = APIRouter(tags=["meta"], dependencies=[Depends(require_auth)])  # needs login


@router.get("/health")
def health(svc: Services = Depends(get_services)):
    return {
        "status": "ok",
        "service": svc.settings.app_name,
        "llm_ready": bool(svc.registry.available_models()),
    }


@private_router.get("/config")
def client_config(svc: Services = Depends(get_services)):
    roles = svc.registry.roles()
    role_names: dict[str, list[str]] = {}
    for role, ref in roles.items():
        role_names.setdefault(ref.id, []).append(role)
    models = [
        {
            "id": ref.id,
            "label": ref.label,
            "name": ref.name,
            "provider": ref.provider,
            "provider_label": PROVIDER_LABELS.get(ref.provider, ref.provider.title()),
            "roles": role_names.get(ref.id, []),
        }
        for ref in svc.registry.available_models()
    ]
    return {
        "app_name": svc.settings.app_name,
        "models": models,
        "default_model": "auto",
        "auto_model": {"reasoning": roles["reasoning"].id, "fast": roles["fast"].id},
        "db_types": svc.settings.allowed_db_types,
        "limits": {
            "row_limit": svc.settings.query_row_limit,
            "query_timeout_seconds": svc.settings.query_timeout_seconds,
            "max_message_chars": svc.settings.max_message_chars,
        },
    }
