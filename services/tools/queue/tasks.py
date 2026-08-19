"""Celery tasks — where slow-path tools actually run, emitting a progress stream.

Tasks build their own registry/executor (they run in worker processes) and write
events to the shared JobStore. Tool errors are captured into the job (not raised),
so a failed ADMET/docking call surfaces as a clean 'failed' event, never a crash.
"""
from __future__ import annotations

from services.tools.catalog import build_registry
from services.tools.context import ExecutionContext
from services.tools.executor import ToolExecutionService
from services.tools.jobs import EventType, JobStatus, event
from services.tools.queue.celery_app import celery_app
from services.tools.store import get_store

# Built once per worker process — includes container tools so they run on workers.
_registry = build_registry()
_executor = ToolExecutionService(_registry)


def _ctx(ctx_dict: dict) -> ExecutionContext:
    return ExecutionContext(
        org_id=ctx_dict.get("org_id", "local-org"),
        project_id=ctx_dict.get("project_id", "local-project"),
        run_id=ctx_dict.get("run_id"),
        version_pins=ctx_dict.get("version_pins", {}),
    )


@celery_app.task(name="glowsky.run_tool_job")
def run_tool_job(job_id: str, tool: str, args: dict, ctx_dict: dict, seed: int | None) -> str:
    store = get_store()
    store.set_status(job_id, JobStatus.RUNNING)
    store.append_event(job_id, event(EventType.RUNNING, tool=tool))
    try:
        result = _executor.execute(tool, args, _ctx(ctx_dict), seed=seed)
        payload = {"output": result.output, "provenance": result.record.as_dict()}
        store.set_result(job_id, payload)
        store.append_event(job_id, event(EventType.COMPLETED, result=payload))
        store.set_status(job_id, JobStatus.COMPLETED)
    except Exception as exc:  # noqa: BLE001 - a worker task must always terminate the job
        # record. Any escaping exception would leave the job RUNNING forever from the
        # client's point of view.
        store.set_error(job_id, str(exc))
        store.append_event(job_id, event(EventType.FAILED, error=str(exc)))
        store.set_status(job_id, JobStatus.FAILED)
    return job_id


@celery_app.task(name="glowsky.run_batch_job")
def run_batch_job(job_id: str, tool: str, items: list[dict], ctx_dict: dict) -> str:
    """Run a tool over many inputs, streaming a per-item event and partial result.

    Phase 0 processes items sequentially; the per-item streaming is identical to what
    a parallel Celery group/chord emits, so the client/UX is unchanged when fan-out
    lands in Phase 2 (docs/13 §4.2). Failed items are reported, never silently dropped.
    """
    store = get_store()
    ctx = _ctx(ctx_dict)
    total = len(items)
    store.set_status(job_id, JobStatus.RUNNING)
    store.append_event(job_id, event(EventType.RUNNING, tool=tool, total=total))

    results: list[dict] = []
    failures = 0
    for i, item_args in enumerate(items):
        try:
            res = _executor.execute(tool, item_args, ctx)
            entry = {"index": i, "args": item_args, "output": res.output,
                     "cache_hit": res.record.cache_hit}
        except Exception as exc:  # noqa: BLE001 - one bad item in a batch must not abort
            # the remaining items; the failure is recorded per-index instead.
            failures += 1
            entry = {"index": i, "args": item_args, "error": str(exc)}
        results.append(entry)
        store.append_event(job_id, event(EventType.ITEM, done=i + 1, total=total, item=entry))

    summary = {"total": total, "succeeded": total - failures, "failed": failures, "results": results}
    store.set_result(job_id, summary)
    store.append_event(job_id, event(EventType.COMPLETED, result=summary))
    store.set_status(job_id, JobStatus.COMPLETED)
    return job_id
