"""Job store — the shared, append-only event log behind streaming (docs/13 §4).

Two backends, one interface:
  • InMemoryJobStore — single-process; used in EAGER/dev/test mode (no broker).
  • RedisJobStore    — cross-process; API and Celery workers share it in production.

The WebSocket endpoint streams by reading events incrementally (by index) until a
terminal status — identical logic for both backends.
"""
from __future__ import annotations

import json
from typing import Protocol

from services.core.config import get_settings
from services.tools.jobs import TERMINAL, JobStatus


class JobStore(Protocol):
    def create(self, job_id: str, tool: str, kind: str, org_id: str) -> None: ...
    def append_event(self, job_id: str, event: dict) -> None: ...
    def set_status(self, job_id: str, status: JobStatus) -> None: ...
    def set_result(self, job_id: str, result) -> None: ...
    def set_error(self, job_id: str, error: str) -> None: ...
    def get(self, job_id: str) -> dict | None: ...
    def events(self, job_id: str) -> list[dict]: ...


class InMemoryJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}

    def create(self, job_id: str, tool: str, kind: str, org_id: str) -> None:
        self._jobs[job_id] = {
            "job_id": job_id, "tool": tool, "kind": kind, "org_id": org_id,
            "status": JobStatus.QUEUED.value, "events": [], "result": None, "error": None,
        }

    def append_event(self, job_id: str, event: dict) -> None:
        self._jobs[job_id]["events"].append(event)

    def set_status(self, job_id: str, status: JobStatus) -> None:
        self._jobs[job_id]["status"] = status.value

    def set_result(self, job_id: str, result) -> None:
        self._jobs[job_id]["result"] = result

    def set_error(self, job_id: str, error: str) -> None:
        self._jobs[job_id]["error"] = error

    def get(self, job_id: str) -> dict | None:
        return self._jobs.get(job_id)

    def events(self, job_id: str) -> list[dict]:
        job = self._jobs.get(job_id)
        return list(job["events"]) if job else []


class RedisJobStore:
    """Cross-process store. Job metadata in a hash; events in a list (append-only)."""

    def __init__(self, url: str) -> None:
        import redis  # lazy: only needed when a broker is configured

        self._r = redis.Redis.from_url(url, decode_responses=True)

    def _k(self, job_id: str) -> str:
        return f"glowsky:job:{job_id}"

    def create(self, job_id: str, tool: str, kind: str, org_id: str) -> None:
        self._r.hset(self._k(job_id), mapping={
            "job_id": job_id, "tool": tool, "kind": kind, "org_id": org_id,
            "status": JobStatus.QUEUED.value, "result": "", "error": "",
        })
        self._r.expire(self._k(job_id), 86400)  # 24h TTL

    def append_event(self, job_id: str, event: dict) -> None:
        self._r.rpush(f"{self._k(job_id)}:events", json.dumps(event))
        self._r.expire(f"{self._k(job_id)}:events", 86400)

    def set_status(self, job_id: str, status: JobStatus) -> None:
        self._r.hset(self._k(job_id), "status", status.value)

    def set_result(self, job_id: str, result) -> None:
        self._r.hset(self._k(job_id), "result", json.dumps(result))

    def set_error(self, job_id: str, error: str) -> None:
        self._r.hset(self._k(job_id), "error", error)

    def get(self, job_id: str) -> dict | None:
        data = self._r.hgetall(self._k(job_id))
        if not data:
            return None
        if data.get("result"):
            data["result"] = json.loads(data["result"])
        data["events"] = self.events(job_id)
        return data

    def events(self, job_id: str) -> list[dict]:
        raw = self._r.lrange(f"{self._k(job_id)}:events", 0, -1)
        return [json.loads(e) for e in raw]


_store: JobStore | None = None


def get_store() -> JobStore:
    """Process-wide singleton, chosen by config. API and (eager) tasks share it."""
    global _store
    if _store is None:
        settings = get_settings()
        _store = RedisJobStore(settings.redis_url) if settings.redis_url else InMemoryJobStore()
    return _store


def is_terminal(job: dict | None) -> bool:
    return bool(job) and job["status"] in {s.value for s in TERMINAL}
