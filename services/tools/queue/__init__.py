"""Slow-path execution: Celery workers + streamed progress (docs/13 §4.3).

Run a worker (production, with Redis configured):
    celery -A services.tools.queue.celery_app worker --loglevel=info

With no GLOWSKY_REDIS_URL set, Celery runs EAGER (in-process) so the slow path works
end-to-end with zero infrastructure for dev/test.
"""
