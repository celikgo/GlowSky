"""Content-addressed result cache (docs/13 §4.2).

Deterministic chemistry is computed once, ever. Key =
hash(tool, version, env_digest, canonical_args[, seed]) — and is TENANT-SCOPED,
because an input structure is itself IP (a global cache would leak its existence).

Phase 0: in-memory implementation behind a swappable interface. Phase 1: Redis
(hot) + object storage (cold). The interface does not change.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

from services.tools.spec import Determinism, ToolSpec


def make_key(spec: ToolSpec, org_id: str, args: dict, seed: int | None) -> str:
    payload = {
        "tool": spec.name,
        "version": spec.version,
        "env": spec.env_digest,
        "org": org_id,  # tenant-scoped
        "args": args,
        "seed": seed,
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def is_cacheable(spec: ToolSpec) -> bool:
    return spec.cacheable and spec.determinism != Determinism.NONDETERMINISTIC


class ResultCache(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any) -> None: ...


class InMemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        return self._store.get(key)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value
