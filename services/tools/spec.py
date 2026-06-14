"""The Tool Contract — the single abstraction the registry, executor, cache,
provenance, and SDK all key off (docs/13 §2)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolCategory(str, Enum):
    CHEMINFORMATICS = "cheminformatics"
    FILTERING = "filtering"
    PROPERTY = "property"
    GENERATIVE = "generative"
    STRUCTURE_BASED = "structure_based"
    RETROSYNTHESIS = "retrosynthesis"
    SEARCH = "search"
    IO = "io"


class ComputeClass(str, Enum):
    """Where/how a tool runs. Drives executor routing (fast path vs worker pool)."""

    CPU_LIGHT = "cpu_light"      # inline, sub-second (canonicalize, descriptors)
    CPU_HEAVY = "cpu_heavy"      # CPU worker pool (conformers, clustering, enumeration)
    GPU = "gpu"                  # GPU worker pool (ML predictors, gnina, generative)
    IO_BOUND = "io_bound"        # IO worker pool (external corpora)
    EXTERNAL_API = "external_api"  # rate-limited connector (retrosynthesis APIs)


class LatencyClass(str, Enum):
    INSTANT = "instant"  # <100ms  -> fast path
    SHORT = "short"      # <10s    -> slow path
    LONG = "long"        # s..min  -> slow path
    BATCH = "batch"      # library-scale map/reduce


class Determinism(str, Enum):
    DETERMINISTIC = "deterministic"      # cacheable on input
    SEEDED = "seeded"                    # cacheable on (input, seed)
    NONDETERMINISTIC = "nondeterministic"  # never cached


class Runtime(str, Enum):
    BUILTIN = "builtin"        # in-process Python (core + trusted self-host plugins)
    CONTAINER = "container"    # sandboxed image (bring-your-own model)  [Phase 3]
    REMOTE_HTTP = "remote_http"  # registered endpoint                  [Phase 3]


class Egress(str, Enum):
    NONE = "none"
    ALLOWLIST = "allowlist"


@dataclass(frozen=True)
class Resources:
    cpu: float = 1.0
    mem_mb: int = 512
    gpu: int = 0
    timeout_s: int = 30


@dataclass(frozen=True)
class ToolSpec:
    """A versioned, typed, schedulable description of one tool capability."""

    name: str
    version: str
    category: ToolCategory
    summary: str
    handler: Callable[..., Any]
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    # execution / scaling metadata
    compute_class: ComputeClass = ComputeClass.CPU_LIGHT
    latency_class: LatencyClass = LatencyClass.INSTANT
    determinism: Determinism = Determinism.DETERMINISTIC
    batchable: bool = False
    cacheable: bool = True
    # resources & runtime (for scheduling + reproducibility)
    resources: Resources = field(default_factory=Resources)
    runtime: Runtime = Runtime.BUILTIN
    env_digest: str = "builtin"   # container digest for CONTAINER tools; pinned for repro
    # safety
    egress: Egress = Egress.NONE
    emits_structures: bool = False  # if True -> outputs pass the validation firewall

    @property
    def qualified_name(self) -> str:
        return f"{self.name}@{self.version}"

    @property
    def is_fast_path(self) -> bool:
        """Inline, synchronous execution is safe only for instant CPU-light tools."""
        return (
            self.compute_class == ComputeClass.CPU_LIGHT
            and self.latency_class == LatencyClass.INSTANT
        )

    def discovery_dict(self) -> dict:
        """Schema surfaced to the agent / LLM tool-calling / UI catalog (no handler)."""
        return {
            "name": self.name,
            "version": self.version,
            "category": self.category.value,
            "description": self.summary,
            "parameters": self.input_schema,
            "compute_class": self.compute_class.value,
            "latency_class": self.latency_class.value,
            "emits_structures": self.emits_structures,
        }
