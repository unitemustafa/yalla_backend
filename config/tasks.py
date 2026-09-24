import logging
import time

from celery import shared_task
from config.celery_utils import log_task_execution

logger = logging.getLogger("config.tasks")


@shared_task(
    bind=True,
    name="config.tasks.delete_storage_file_task",
    queue="default",
    max_retries=2,
    soft_time_limit=20,
    time_limit=40,
)
def delete_storage_file_task(self, storage_alias: str, name: str):
    """Remove an unreferenced media file in the background without holding web workers."""
    from config.media_cleanup import (
        get_storage_by_identifier,
        storage_name_is_referenced,
    )

    t0 = time.perf_counter()
    attempt = self.request.retries + 1

    try:
        storage = get_storage_by_identifier(storage_alias)
        if name and not storage_name_is_referenced(name, storage=storage):
            if storage.exists(name):
                storage.delete(name)

        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name, self.request.id, name, attempt, "success", duration_ms
        )
        return {"status": "success", "file": name}

    except Exception as exc:
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            name,
            attempt,
            "permanent_failure",
            duration_ms,
            error_type=exc.__class__.__name__,
        )
        return {"status": "failed", "error": str(exc)}
