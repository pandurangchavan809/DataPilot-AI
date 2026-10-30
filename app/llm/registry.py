"""Provider + model registry.

All providers speak the OpenAI Chat Completions protocol, so one SDK client
per provider is enough. Add a provider by listing it in LLM_PROVIDERS and
setting <NAME>_API_KEY, <NAME>_MODELS and <NAME>_BASE_URL.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from openai import OpenAI

from ..config import Settings
from ..core.errors import ValidationError

logger = logging.getLogger(__name__)

DEFAULT_BASE_URLS = {
    "nebius": "https://api.tokenfactory.nebius.com/v1/",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openai": "https://api.openai.com/v1",
}

PROVIDER_LABELS = {"nebius": "Nebius Token Factory", "gemini": "Google Gemini", "openai": "OpenAI"}


@dataclass(frozen=True)
class ModelRef:
    provider: str
    name: str

    @property
    def id(self) -> str:
        return f"{self.provider}:{self.name}"

    @property
    def label(self) -> str:
        return self.name.rsplit("/", 1)[-1]

    @classmethod
    def parse(cls, ref: str) -> "ModelRef":
        provider, sep, name = ref.partition(":")
        if not sep or not provider or not name:
            raise ValidationError(f"Invalid model reference '{ref}'. Expected '<provider>:<model>'.")
        return cls(provider.strip().lower(), name.strip())


class ProviderRegistry:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._clients: dict[str, OpenAI] = {}
        for provider in settings.llm_providers:
            api_key, base_url = settings.provider_credentials(provider)
            base_url = base_url or DEFAULT_BASE_URLS.get(provider, "")
            if not api_key or not base_url:
                logger.info("LLM provider '%s' disabled (missing API key or base URL)", provider)
                continue
            self._clients[provider] = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=settings.llm_timeout_seconds,
                max_retries=2,  # SDK retries 429/5xx/connection errors with backoff
            )
        if not self._clients:
            logger.warning("No LLM providers are configured; chat will be unavailable.")

    def client(self, provider: str) -> OpenAI | None:
        return self._clients.get(provider)

    def is_enabled(self, ref: ModelRef) -> bool:
        return ref.provider in self._clients

    def roles(self) -> dict[str, ModelRef]:
        s = self._settings
        return {
            "primary": ModelRef.parse(s.llm_primary),
            "secondary": ModelRef.parse(s.llm_secondary),
            "reasoning": ModelRef.parse(s.reasoning_model),
            "fast": ModelRef.parse(s.fast_model),
        }

    def available_models(self) -> list[ModelRef]:
        """Role models first, then each provider's <NAME>_MODELS list."""
        refs = list(self.roles().values())
        for provider in self._clients:
            refs.extend(ModelRef(provider, name) for name in self._settings.provider_models(provider))
        seen: dict[str, ModelRef] = {}
        for ref in refs:
            if self.is_enabled(ref) and ref.id not in seen:
                seen[ref.id] = ref
        return list(seen.values())

    def resolve_override(self, model_id: str | None) -> ModelRef | None:
        """Validate a user-selected model; only models exposed to the UI are allowed."""
        if not model_id or model_id == "auto":
            return None
        allowed = {ref.id: ref for ref in self.available_models()}
        if model_id not in allowed:
            raise ValidationError(f"Model '{model_id}' is not available.")
        return allowed[model_id]
