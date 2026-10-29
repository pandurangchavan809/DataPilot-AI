"""Centralised, validated application settings.

Every tunable lives in the environment (.env). Settings are validated once at
startup so misconfiguration fails fast instead of on the first request.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_DIR / ".env"

CsvList = Annotated[list[str], NoDecode]

# Provider credentials are discovered dynamically ({NAME}_API_KEY), so make
# sure the .env values are visible through os.environ as well.
load_dotenv(ENV_FILE, override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- App -----------------------------------------------------------------
    app_name: str = "DataPilot AI"
    app_env: str = "development"
    secret_key: str = Field(min_length=16)
    log_level: str = "INFO"
    cors_origins: CsvList = ["http://localhost:5173"]

    # --- LLM providers (OpenAI-compatible) -----------------------------------
    # Each name N in this list is configured via N_API_KEY and N_BASE_URL.
    llm_providers: CsvList = ["nebius", "gemini", "openai"]

    # --- LLM roles -----------------------------------------------------------
    # Model references are "<provider>:<model-name>".
    llm_primary: str = "nebius:nvidia/Llama-3_3-Nemotron-Super-49B-v1_5"
    llm_secondary: str = "gemini:gemini-2.5-flash"
    llm_reasoning: str = ""  # SQL generation; falls back to primary
    llm_fast: str = ""  # routing, insights, charts; falls back to primary
    llm_available_models: CsvList = []
    llm_temperature: float = 0.1
    llm_timeout_seconds: float = 60.0
    llm_max_tokens: int = 4096

    # --- Agents --------------------------------------------------------------
    max_sql_retries: int = 2
    schema_full_context_max_tables: int = 15
    schema_sample_rows: int = 3
    chat_history_turns: int = 6

    # --- Data access / safety ------------------------------------------------
    demo_db_path: Path = BACKEND_DIR / "data" / "demo.db"
    query_row_limit: int = 1000
    query_timeout_seconds: int = 15
    allowed_db_types: CsvList = ["sqlite_demo", "postgresql", "mysql"]

    # --- Sessions / infra ----------------------------------------------------
    session_backend: str = "memory"  # memory | redis
    session_ttl_minutes: int = 60
    redis_url: str = ""
    engine_cache_size: int = 64
    rate_limit: str = "30/minute"
    rate_limit_storage_uri: str = "memory://"
    proxy_fix_hops: int = 0  # set to 1 behind nginx / a load balancer
    max_message_chars: int = 4000

    @field_validator(
        "cors_origins", "llm_providers", "llm_available_models", "allowed_db_types", mode="before"
    )
    @classmethod
    def _split_csv(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("demo_db_path", mode="after")
    @classmethod
    def _resolve_path(cls, value: Path) -> Path:
        return value if value.is_absolute() else (BACKEND_DIR / value).resolve()

    @field_validator("session_backend")
    @classmethod
    def _check_backend(cls, value: str) -> str:
        if value not in {"memory", "redis"}:
            raise ValueError("SESSION_BACKEND must be 'memory' or 'redis'")
        return value

    @property
    def reasoning_model(self) -> str:
        return self.llm_reasoning or self.llm_primary

    @property
    def fast_model(self) -> str:
        return self.llm_fast or self.llm_primary

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def provider_credentials(self, provider: str) -> tuple[str, str]:
        prefix = provider.upper()
        return os.getenv(f"{prefix}_API_KEY", ""), os.getenv(f"{prefix}_BASE_URL", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
