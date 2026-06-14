"""The gateway façade. Callers use this and nothing lower-level.

Resolves a route for the task class, falls back to the offline mock when the routed
provider has no credentials configured (so the product always runs), dispatches to
the right provider, and returns a normalized response. Keys never leave keys.py.
"""
from __future__ import annotations

from services.core.config import Settings, get_settings
from services.llm_gateway.keys import KeyStore
from services.llm_gateway.providers import LiteLLMProvider, MockProvider, Provider
from services.llm_gateway.routing import Router
from services.llm_gateway.types import (
    CompletionRequest,
    CompletionResponse,
    ModelRoute,
    TaskClass,
)


class LLMGateway:
    def __init__(self, settings: Settings | None = None, org_id: str | None = None) -> None:
        settings = settings or get_settings()
        # When scoped to an org, the org's stored BYO-LLM keys/routes take precedence
        # over env defaults (graceful fallback to mock still applies).
        resolver = None
        if org_id is not None:
            from services.llm_gateway.credentials import CredentialResolver

            resolver = CredentialResolver(org_id)
        self._keys = KeyStore(settings, resolver)
        self._router = Router(settings, resolver)
        self._mock: Provider = MockProvider()
        self._litellm: Provider = LiteLLMProvider(self._keys)

    def _select(self, task_class: TaskClass) -> tuple[Provider, ModelRoute]:
        route = self._router.resolve(task_class)
        if route.provider == "mock" or not self._keys.has_credentials(route.provider):
            # Graceful degradation: no key -> offline mock instead of a hard failure.
            return self._mock, ModelRoute("mock", "mock", task_class)
        return self._litellm, route

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        provider, route = self._select(req.task_class)
        return await provider.complete(req, route)

    def route_for(self, task_class: TaskClass) -> str:
        """Expose the resolved 'provider/model' for provenance/UX (no secrets)."""
        _, route = self._select(task_class)
        return f"{route.provider}/{route.model}"
