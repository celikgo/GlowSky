"""Versioned tool registry (docs/13 §3).

Holds ToolSpecs by name+version. Built-ins register at boot; custom/org tools load
from manifests in Phase 3. Projects can pin a version for exact reproducibility.
"""
from __future__ import annotations

from services.tools.spec import ToolSpec


class ToolRegistry:
    def __init__(self) -> None:
        # name -> {version -> spec}
        self._tools: dict[str, dict[str, ToolSpec]] = {}
        self._latest: dict[str, str] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools.setdefault(spec.name, {})[spec.version] = spec
        # Track latest by simple tuple-of-ints semver compare.
        cur = self._latest.get(spec.name)
        if cur is None or _semver(spec.version) > _semver(cur):
            self._latest[spec.name] = spec.version

    def resolve(self, name: str, version: str | None = None) -> ToolSpec:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        version = version or self._latest[name]
        if version not in self._tools[name]:
            raise KeyError(f"unknown version {version!r} for tool {name}")
        return self._tools[name][version]

    def list(self) -> list[ToolSpec]:
        return [self.resolve(name) for name in self._tools]  # latest of each

    def specs(self) -> list[dict]:
        return [t.discovery_dict() for t in self.list()]


def _semver(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in v.split("."))
    except ValueError:
        return (0,)
