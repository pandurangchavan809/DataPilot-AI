"""Application service container, built once per process."""

from __future__ import annotations

from dataclasses import dataclass

from flask import current_app

from .config import Settings
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

    @classmethod
    def build(cls, settings: Settings) -> "Services":
        registry = ProviderRegistry(settings)
        return cls(
            settings=settings,
            registry=registry,
            llm=LLMGateway(settings, registry),
            connections=ConnectionManager(settings, build_session_store(settings)),
        )


def services() -> Services:
    return current_app.extensions["datapilot"]
