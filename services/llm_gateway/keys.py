"""Key resolution boundary.

Phase 0: keys come from environment-backed Settings. Phase 1+: this same interface
is backed by a KMS/secrets manager, with rows storing only opaque references
(see docs/07-security-privacy.md §2). Callers receive a key only at the moment of
use; keys are never logged, never returned to clients, never placed in traces.
"""
from __future__ import annotations

from typing import Protocol

from services.core.config import Settings, get_settings


class Resolver(Protocol):
    """An org-scoped credential source consulted ahead of env defaults."""

    def api_key(self, provider: str) -> str | None: ...
    def base_url(self, provider: str) -> str | None: ...


class KeyStore:
    """Resolves provider credentials. An optional org resolver (DB-backed BYO-LLM keys)
    takes precedence; env-configured Settings are the fallback."""

    def __init__(self, settings: Settings | None = None, resolver: Resolver | None = None) -> None:
        self._settings = settings or get_settings()
        self._resolver = resolver

    def api_key(self, provider: str) -> str | None:
        if self._resolver:
            key = self._resolver.api_key(provider)
            if key:
                return key
        return {
            "anthropic": self._settings.anthropic_api_key,
            "openai": self._settings.openai_api_key,
            "groq": self._settings.groq_api_key,
            "local": self._settings.local_api_key,
        }.get(provider)

    def base_url(self, provider: str) -> str | None:
        if self._resolver:
            url = self._resolver.base_url(provider)
            if url:
                return url
        if provider == "local":
            return self._settings.local_base_url
        return None

    def has_credentials(self, provider: str) -> bool:
        """The mock provider needs no key; everything else needs at least a key/base_url."""
        if provider == "mock":
            return True
        if provider == "local":
            return bool(self.base_url("local"))
        return bool(self.api_key(provider))
