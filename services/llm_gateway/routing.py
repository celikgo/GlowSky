"""Task-class -> model routing. Reads defaults from settings; overridable per call.

A "provider/model" string (e.g. "anthropic/claude-opus-4-8" or "mock/mock") is
parsed into a ModelRoute. Per-project overrides (docs/06 ModelRoute) layer on here in Phase 1.
"""
from __future__ import annotations

from typing import Protocol

from services.core.config import Settings, get_settings
from services.llm_gateway.types import ModelRoute, TaskClass


class RouteResolver(Protocol):
    def route(self, task_class: TaskClass) -> str | None: ...


def _parse(spec: str, task_class: TaskClass) -> ModelRoute:
    provider, _, model = spec.partition("/")
    if not provider or not model:
        raise ValueError(f"invalid route spec {spec!r}; expected 'provider/model'")
    return ModelRoute(provider=provider, model=model, task_class=task_class)


class Router:
    """Resolves task-class -> model. An org route override (DB) wins; otherwise the
    env-configured default applies."""

    def __init__(self, settings: Settings | None = None, resolver: RouteResolver | None = None) -> None:
        self._settings = settings or get_settings()
        self._resolver = resolver

    def resolve(self, task_class: TaskClass) -> ModelRoute:
        if self._resolver:
            override = self._resolver.route(task_class)
            if override:
                return _parse(override, task_class)
        spec = {
            TaskClass.REASONING: self._settings.route_reasoning,
            TaskClass.FAST_TRIAGE: self._settings.route_fast_triage,
            TaskClass.CODEGEN: self._settings.route_codegen,
        }[task_class]
        return _parse(spec, task_class)
