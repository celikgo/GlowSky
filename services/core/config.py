"""Central configuration. All settings are env-driven (prefix GLOWSKY_).

Secrets (provider API keys) are read here but MUST never be logged or returned
to clients. See services.llm_gateway.keys for the access boundary.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GLOWSKY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database ---
    database_url: str = "sqlite:///glowsky.db"

    # --- BYO-LLM provider credentials (Phase 0: env-backed key store) ---
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    groq_api_key: str | None = None
    local_base_url: str | None = None
    local_api_key: str | None = None

    # --- Model routing: "provider/model" per task class ---
    route_reasoning: str = "mock/mock"
    route_fast_triage: str = "mock/mock"
    route_codegen: str = "mock/mock"

    # --- Slow-path queue & streaming ---
    # If redis_url is set, Celery uses it as broker+backend and the shared JobStore
    # is Redis-backed (cross-process: API + workers). If blank, Celery runs EAGER
    # (in-process, no broker) with an in-memory store — the zero-dependency dev/test mode.
    redis_url: str | None = None

    @property
    def celery_eager(self) -> bool:
        return not self.redis_url

    # --- Container tools (extensibility) ---
    # Directory scanned for `glowsky-tool.yaml` manifests at startup. Each becomes a
    # sandboxed, agent-callable tool. Blank => no container tools loaded.
    tools_dir: str | None = None

    # --- App ---
    app_name: str = "Glowsky"
    environment: str = "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
