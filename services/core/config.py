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

    # Bounds for the DEFAULT (no-Redis) in-process stores, which have no TTL. Without a
    # cap the InMemoryJobStore (full event log + result per job) and InMemoryCache grow
    # monotonically until the process is OOM-killed. Both evict least-recently-used past
    # the cap. The Redis backends instead rely on a 24h TTL and are unaffected.
    job_store_max: int = 2048
    result_cache_max: int = 4096

    # --- Container tools (extensibility) ---
    # Directory scanned for `glowsky-tool.yaml` manifests at startup. Each becomes a
    # sandboxed, agent-callable tool. Blank => no container tools loaded.
    tools_dir: str | None = None

    # --- Chemistry prediction/engine backends (adapter-gated) ---
    # "none" (default) => the tool stays "not configured" and never fabricates values.
    # ADMET: "rdkit" enables the offline RDKit-QSPR estimator (ESOL + heuristics).
    admet_backend: str = "none"  # none|rdkit
    # Docking: "vina" enables the AutoDock Vina subprocess backend (needs vina+obabel).
    docking_backend: str = "none"  # none|vina
    vina_bin: str = "vina"
    obabel_bin: str = "obabel"

    # --- Secrets at rest ---
    # Fernet key (44-char urlsafe-base64) used to encrypt stored BYO-LLM credentials.
    # Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # If unset, a deterministic DEV key is derived — fine for local dev, NEVER production.
    secret_key: str | None = None

    # --- Nakitte platform auth (the sole auth provider) ---
    # Every request in every environment authenticates with a nakitte-carbon-auth access
    # token: an RS256 JWT verified against that service's JWKS endpoint. Identity (user /
    # tenant / roles) comes from the token; Glowsky JIT-provisions a local org+user mirror
    # so its tenant-scoped persistence and FKs resolve. There is no local identity store
    # and no auth bypass — dev points GLOWSKY_NAKITTE_JWKS_URL at a running carbon-auth.
    nakitte_jwks_url: str = "http://localhost:8081/.well-known/jwks.json"
    nakitte_jwt_issuer: str | None = None  # enforced as the `iss` claim when set
    nakitte_jwt_audience: str = "carbon-platform"
    # Base URL of carbon-auth for the login proxy (POST /auth/login, /auth/refresh). Same
    # service that serves the JWKS; the desktop logs in through Glowsky so this URL stays
    # server-side. Glowsky never stores credentials — it forwards them and relays the token.
    nakitte_auth_url: str = "http://localhost:8081"

    # --- Docking receptor confinement ---
    # The `dock` tool only accepts receptor files resolving under this directory, so a
    # caller-supplied receptor_ref can never traverse the worker filesystem (path-oracle
    # / arbitrary-read guard). Matches the ./examples/docking mount in the docking image.
    docking_receptors_dir: str = "examples/docking"

    # --- CORS ---
    # Origins allowed to call the API from a browser/webview. The desktop app's webview
    # (Tauri) and the Vite dev server are cross-origin to the API, so they must be listed
    # or the browser blocks every request. Comma-separated; "*" allows any origin.
    cors_origins: str = (
        "http://localhost:1420,http://127.0.0.1:1420,tauri://localhost,http://tauri.localhost"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # --- App ---
    app_name: str = "Glowsky"
    # Fail-SAFE default: an unset environment is treated as production, so a self-host that
    # follows the shipped compose without setting GLOWSKY_ENVIRONMENT/GLOWSKY_SECRET_KEY
    # refuses to boot (validate_secret_config) rather than silently encrypting customers'
    # BYO-LLM keys under the public in-source dev key (GS-H1). Local dev / CI must opt IN to
    # the dev key by setting GLOWSKY_ENVIRONMENT to a dev-tier value (dev/test/ci/…).
    environment: str = "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
