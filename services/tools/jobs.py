"""Job and event types for the slow path (docs/13 §4).

A slow-path tool call becomes a Job. As it runs on a worker it emits an ordered
stream of JobEvents (queued -> running -> progress* -> completed|failed) that the
WebSocket endpoint relays live to the client.
"""
from __future__ import annotations

from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


TERMINAL = {JobStatus.COMPLETED, JobStatus.FAILED}


class EventType(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PROGRESS = "progress"   # incremental — carries {done, total, ...} and/or a partial result
    ITEM = "item"           # one batch item finished — carries its result
    COMPLETED = "completed"  # terminal — carries the final result
    FAILED = "failed"       # terminal — carries the error


def event(type_: EventType, **payload) -> dict:
    """Build a JSON-serializable event. (No timestamp here — the runtime stamps it;
    keeping events deterministic also keeps tests stable.)"""
    return {"type": type_.value, **payload}
