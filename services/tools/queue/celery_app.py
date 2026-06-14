"""The Celery application.

Broker + result backend come from GLOWSKY_REDIS_URL. If unset, EAGER mode runs tasks
synchronously in-process (no broker) — the default for dev/test. Worker pools map to
compute classes via queues (worker-cpu / worker-gpu / worker-io) in deployment;
Phase 0 uses a single default queue.
"""
from __future__ import annotations

from celery import Celery
from celery.signals import worker_process_init

from services.core.config import get_settings

_settings = get_settings()
_broker = _settings.redis_url or "memory://"
_backend = _settings.redis_url or "cache+memory://"

celery_app = Celery("glowsky", broker=_broker, backend=_backend)
celery_app.conf.update(
    task_always_eager=_settings.celery_eager,   # run in-process when no Redis
    task_eager_propagates=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_default_queue="default",
    # In production, route heavy tools to dedicated pools:
    #   task_routes={"glowsky.run_tool_job": {"queue": "cpu"}, ...}
)

@worker_process_init.connect
def _configure_backends_on_worker(**_kwargs) -> None:
    """Distributed workers run heavy tools (predict_admet/dock); configure the same
    adapter-gated backends the API uses. Eager mode is handled by the API lifespan."""
    from services.chemistry.adapters.wiring import configure_backends

    configure_backends()


# Ensure task modules are imported so the workers register them.
celery_app.autodiscover_tasks(["services.tools.queue"])
import services.tools.queue.tasks  # noqa: E402,F401
