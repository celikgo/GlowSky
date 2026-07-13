"""Tool Execution Service — the dispatcher (docs/13 §4).

The orchestrator/agent calls execute(name, args, ctx) and never knows WHERE a tool
ran. Responsibilities, in order:
  1. resolve spec (honoring project version pins)
  2. cache lookup (deterministic tools, tenant-scoped)
  3. quota / fairness  [Phase 1 hook]
  4. route by compute class: fast path (inline) vs slow path (queue)  [Phase 1 queue]
  5. validation firewall on any emitted structures
  6. record provenance + populate cache

Phase 0 runs everything INLINE so the slice is self-contained and testable. Switching
CPU_HEAVY/GPU/LONG/BATCH tools to the Celery slow path (docs/13 §4.3) changes only
_dispatch() — the orchestrator is untouched.
"""
from __future__ import annotations

import time
import uuid
from enum import Enum

from services.tools.cache import InMemoryCache, ResultCache, is_cacheable, make_key
from services.tools.context import ExecutionContext
from services.tools.jobs import EventType, event
from services.tools.registry import ToolRegistry
from services.tools.result import ExecutionRecord, ToolResult
from services.tools.spec import ToolSpec
from services.tools.store import get_store


class ExecutionMode(str, Enum):
    INLINE = "inline"  # run synchronously here (Phase 0 / single-node self-host)
    QUEUE = "queue"    # dispatch slow-path tools to Celery workers (Phase 1+)


class ToolExecutionService:
    def __init__(
        self,
        registry: ToolRegistry,
        cache: ResultCache | None = None,
        mode: ExecutionMode = ExecutionMode.INLINE,
    ) -> None:
        self._reg = registry
        self._cache = cache or InMemoryCache()
        self._mode = mode

    @property
    def registry(self) -> ToolRegistry:
        """The tool registry this service dispatches to (read-only accessor for the agent)."""
        return self._reg

    def execute(
        self,
        name: str,
        args: dict,
        ctx: ExecutionContext | None = None,
        *,
        seed: int | None = None,
    ) -> ToolResult:
        ctx = ctx or ExecutionContext()
        spec = self._reg.resolve(name, ctx.version_pins.get(name))

        # 2. cache lookup --------------------------------------------------
        cache_key = None
        if is_cacheable(spec):
            cache_key = make_key(spec, ctx.org_id, args, seed)
            cached = self._cache.get(cache_key)
            if cached is not None:
                return ToolResult(
                    output=cached,
                    record=self._record(spec, args, seed, cache_hit=True, duration_ms=0.0),
                )

        # 3. quota / fairness check would go here (docs/13 §7).

        # 4. route + run ---------------------------------------------------
        start = time.perf_counter()
        try:
            output = self._dispatch(spec, args, seed)
        except Exception as exc:
            rec = self._record(
                spec, args, seed, cache_hit=False,
                duration_ms=(time.perf_counter() - start) * 1000, error=str(exc),
            )
            raise ToolExecutionError(spec, str(exc), rec) from exc
        duration_ms = (time.perf_counter() - start) * 1000

        # 5. validation firewall on emitted structures ---------------------
        if spec.emits_structures:
            _firewall_validate(output)

        # 6. provenance + cache --------------------------------------------
        if cache_key is not None:
            self._cache.set(cache_key, output)
        return ToolResult(
            output=output,
            record=self._record(spec, args, seed, cache_hit=False, duration_ms=duration_ms),
        )

    # --- slow path: submit a job, stream results elsewhere ------------------
    @staticmethod
    def _ctx_dict(ctx: ExecutionContext) -> dict:
        return {
            "org_id": ctx.org_id, "project_id": ctx.project_id,
            "run_id": ctx.run_id, "version_pins": ctx.version_pins,
        }

    def submit(
        self, name: str, args: dict, ctx: ExecutionContext | None = None,
        *, seed: int | None = None,
    ) -> str:
        """Enqueue a single slow-path tool call. Returns a job_id to stream/poll.
        Eager mode runs it inline now; with Redis it lands on a worker."""
        ctx = ctx or ExecutionContext()
        self._reg.resolve(name, ctx.version_pins.get(name))  # validate existence early
        from services.tools.queue.tasks import run_tool_job

        job_id = uuid.uuid4().hex
        store = get_store()
        store.create(job_id, tool=name, kind="single")
        store.append_event(job_id, event(EventType.QUEUED, tool=name))
        run_tool_job.delay(job_id, name, args, self._ctx_dict(ctx), seed)
        return job_id

    def submit_batch(
        self, name: str, items: list[dict], ctx: ExecutionContext | None = None,
    ) -> str:
        """Enqueue a tool over many inputs; per-item results stream as they complete."""
        ctx = ctx or ExecutionContext()
        self._reg.resolve(name, ctx.version_pins.get(name))
        from services.tools.queue.tasks import run_batch_job

        job_id = uuid.uuid4().hex
        store = get_store()
        store.create(job_id, tool=name, kind="batch")
        store.append_event(job_id, event(EventType.QUEUED, tool=name, total=len(items)))
        run_batch_job.delay(job_id, name, items, self._ctx_dict(ctx))
        return job_id

    # --- routing -------------------------------------------------------------
    def _dispatch(self, spec: ToolSpec, args: dict, seed: int | None):
        """Fast path inline; slow path queued (Phase 1). Phase 0: all inline."""
        if self._mode is ExecutionMode.QUEUE and not spec.is_fast_path:
            return self._dispatch_slow(spec, args, seed)
        return self._run_handler(spec, args, seed)

    def _dispatch_slow(self, spec: ToolSpec, args: dict, seed: int | None):
        # Phase 1: enqueue to the matching worker pool (worker-cpu/-gpu/-io) and
        # stream results back. See services/tools/queue/. For now, run inline.
        return self._run_handler(spec, args, seed)

    @staticmethod
    def _run_handler(spec: ToolSpec, args: dict, seed: int | None):
        kwargs = dict(args)
        if spec.determinism.value == "seeded" and seed is not None:
            kwargs["seed"] = seed
        return spec.handler(**kwargs)

    @staticmethod
    def _record(spec, args, seed, *, cache_hit, duration_ms, error=None) -> ExecutionRecord:
        return ExecutionRecord(
            tool=spec.name,
            version=spec.version,
            compute_class=spec.compute_class.value,
            determinism=spec.determinism.value,
            env_digest=spec.env_digest,
            input_hash=make_key(spec, "_provenance", args, seed)[:16],
            cache_hit=cache_hit,
            duration_ms=round(duration_ms, 3),
            seed=seed,
            error=error,
        )


class ToolExecutionError(RuntimeError):
    def __init__(self, spec: ToolSpec, message: str, record: ExecutionRecord) -> None:
        super().__init__(f"{spec.qualified_name}: {message}")
        self.spec = spec
        self.record = record


def _firewall_validate(output) -> None:
    """Defense-in-depth: every 'smiles' a tool emits must pass RDKit validation.
    A tool that claims emits_structures may never surface an invalid structure."""
    from services.chemistry.validation import validate_and_canonicalize

    def walk(node):
        if isinstance(node, dict):
            if "smiles" in node and isinstance(node["smiles"], str):
                if not validate_and_canonicalize(node["smiles"]).valid:
                    raise ValueError(f"firewall: tool emitted invalid structure {node['smiles']!r}")
            for v in node.values():
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)

    walk(output)
