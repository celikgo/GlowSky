"""Org-scoped resolution of stored BYO-LLM credentials and route overrides.

Reads the encrypted provider keys and per-org model-route overrides from the database,
decrypting keys only at the moment of use (never logged, never returned to clients).
The gateway consults a resolver first and falls back to env-configured defaults, so an
org that has stored its own keys uses them while everyone else stays on the defaults.
"""
from __future__ import annotations

from sqlalchemy import select

from services.core.crypto import decrypt
from services.core.db import session_scope
from services.core.models import LLMProviderCredential, ModelRouteOverride
from services.llm_gateway.types import TaskClass


class CredentialResolver:
    """DB-backed lookups for one org. Each method opens a short read transaction."""

    def __init__(self, org_id: str) -> None:
        self._org = org_id

    def _credential(self, provider: str) -> LLMProviderCredential | None:
        with session_scope() as s:
            return s.scalar(
                select(LLMProviderCredential).where(
                    LLMProviderCredential.org_id == self._org,
                    LLMProviderCredential.provider == provider,
                    LLMProviderCredential.status == "active",
                )
            )

    def api_key(self, provider: str) -> str | None:
        cred = self._credential(provider)
        return decrypt(cred.encrypted_secret) if cred else None

    def base_url(self, provider: str) -> str | None:
        cred = self._credential(provider)
        return cred.base_url if cred else None

    def route(self, task_class: TaskClass) -> str | None:
        with session_scope() as s:
            row = s.scalar(
                select(ModelRouteOverride).where(
                    ModelRouteOverride.org_id == self._org,
                    ModelRouteOverride.task_class == task_class.value,
                )
            )
            return f"{row.provider}/{row.model}" if row else None
