"""Local-stack telemetry only; no SQL text, task payloads or credentials."""

import json
import logging
import time

from celery.signals import before_task_publish, task_prerun, task_postrun
from config.observability import JsonFormatter


class PerformanceFormatter(JsonFormatter):
    def format(self, record):
        payload = json.loads(super().format(record))
        for key in ("task_name", "status", "duration_ms", "queue_wait_ms", "attempt"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload)


@before_task_publish.connect
def stamp(headers=None, **kwargs):
    if headers is not None:
        headers["perf_published_at"] = time.time()


@task_prerun.connect
def started(task=None, **kwargs):
    task.request.perf_started = time.monotonic()
    published = (task.request.headers or {}).get("perf_published_at")
    task.request.perf_wait_ms = (time.time() - published) * 1000 if published else None


@task_postrun.connect
def finished(task=None, state=None, **kwargs):
    logging.getLogger("performance.tasks").info(
        "task_finished",
        extra={
            "task_name": task.name,
            "status": state,
            "duration_ms": (
                time.monotonic()
                - getattr(task.request, "perf_started", time.monotonic())
            )
            * 1000,
            "queue_wait_ms": getattr(task.request, "perf_wait_ms", None),
        },
    )
