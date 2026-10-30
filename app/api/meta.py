"""Health and client bootstrap configuration."""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..llm.registry import PROVIDER_LABELS
from ..services import services
from .deps import require_auth

bp = Blueprint("meta", __name__)  # public
private_bp = Blueprint("meta_private", __name__)  # needs login
private_bp.before_request(require_auth)


@bp.get("/health")
def health():
    svc = services()
    return jsonify(
        status="ok",
        service=svc.settings.app_name,
        llm_ready=bool(svc.registry.available_models()),
    )


@private_bp.get("/config")
def client_config():
    svc = services()
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
    return jsonify(
        app_name=svc.settings.app_name,
        models=models,
        default_model="auto",
        auto_model={"reasoning": roles["reasoning"].id, "fast": roles["fast"].id},
        db_types=svc.settings.allowed_db_types,
        limits={
            "row_limit": svc.settings.query_row_limit,
            "query_timeout_seconds": svc.settings.query_timeout_seconds,
            "max_message_chars": svc.settings.max_message_chars,
        },
    )
