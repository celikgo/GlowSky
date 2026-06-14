"""Tool execution results and the provenance record they carry (docs/13 §5)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionRecord:
    """Provenance for one tool execution — the unit that powers reproducibility,
    the transparency UI, and notebook export."""

    tool: str
    version: str
    compute_class: str
    determinism: str
    env_digest: str
    input_hash: str
    cache_hit: bool
    duration_ms: float
    seed: int | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class ToolResult:
    output: Any
    record: ExecutionRecord
    meta: dict = field(default_factory=dict)
