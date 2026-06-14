"""Execution context — tenancy, run linkage, and version pins carried through a call."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExecutionContext:
    org_id: str = "local-org"
    project_id: str | None = "local-project"
    run_id: str | None = None
    # Project-pinned tool versions for reproducibility: {tool_name: version}
    version_pins: dict[str, str] = field(default_factory=dict)
    # Future: priority class, compute budget, quota handle (docs/13 §7).
