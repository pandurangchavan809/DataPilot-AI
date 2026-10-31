"""Application service container, built once per process."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from .auth import AuthService, UserStore
from .config import Settings
from .core.rate_limit import RateLimiter
from .db.manager import ConnectionManager
from .db.session_store import build_session_store
from .llm.gateway import LLMGateway
from .llm.registry import ProviderRegistry


@dataclass
class Services:
    settings: Settings
    registry: ProviderRegistry
    llm: LLMGateway
    connections: ConnectionManager
    auth: AuthService
    limiter: RateLimiter

    @classmethod
    def build(cls, settings: Settings) -> "Services":
        registry = ProviderRegistry(settings)
        return cls(
            settings=settings,
            registry=registry,
            llm=LLMGateway(settings, registry),
            connections=ConnectionManager(settings, build_session_store(settings)),
            auth=AuthService(settings, UserStore(settings.auth_db_path)),
            limiter=RateLimiter(settings.rate_limit_storage_uri),
        )


def get_services(request: Request) -> Services:
    return request.app.state.services
