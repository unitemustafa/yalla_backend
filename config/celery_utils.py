import logging
import random
import time
from typing import Any, Optional

from config.redis_client import get_redis_client

logger = logging.getLogger("celery.tasks")


def calculate_backoff(
    retries: int,
    base: float = 2.0,
    max_backoff: float = 120.0,
    jitter: bool = True,
    mode: str = "full",
) -> float:
    """Calculate exponential backoff with jitter based on AWS Architecture best practices.

    Modes:
      - 'full': sleep = random.uniform(min_floor, ceiling)
      - 'equal': sleep = ceiling/2 + random.uniform(0, ceiling/2)
      - 'none' or jitter=False: sleep = ceiling
    where ceiling = min(max_backoff, base * (2 ** retries))
    """
    ceiling = min(max_backoff, base * (2**retries))
    if not jitter or mode == "none":
        return round(ceiling, 2)
    if mode == "equal":
        half = ceiling / 2.0
        sleep_time = half + random.uniform(0.0, half)
    else:  # default 'full' jitter
        floor = min(0.5, ceiling)
        sleep_time = random.uniform(floor, ceiling)
    return round(sleep_time, 2)


def record_task_metric(task_name: str, status: str, duration_ms: float):
    """Store operational metrics in Redis for queue and task observability."""
    try:
        r = get_redis_client("default")
        pipe = r.pipeline()
        date_hour = time.strftime("%Y%m%d%H")
        pipe.hincrby(f"yalla:metrics:task:{task_name}:{date_hour}", status, 1)
        pipe.hincrbyfloat(
            f"yalla:metrics:task:{task_name}:{date_hour}",
            "total_duration_ms",
            duration_ms,
        )
        pipe.expire(f"yalla:metrics:task:{task_name}:{date_hour}", 86400 * 7)
        pipe.execute()
    except Exception:
        # Observability should never fail the execution of a business task
        pass


def log_task_execution(
    task_name: str,
    task_id: str,
    entity_id: Any,
    attempt: int,
    status: str,
    duration_ms: float,
    error_type: Optional[str] = None,
):
    """Output structured JSON-compatible log entry with required schema."""
    extra = {
        "task_name": task_name,
        "task_id": str(task_id),
        "entity_id": str(entity_id) if entity_id is not None else "none",
        "attempt": attempt,
        "status": status,
        "duration_ms": round(duration_ms, 2),
    }
    if error_type:
        extra["error_type"] = error_type

    record_task_metric(task_name, status, duration_ms)

    if status == "success":
        logger.info(
            "Task %s completed successfully for entity %s",
            task_name,
            entity_id,
            extra=extra,
        )
    elif status == "retry":
        logger.warning(
            "Task %s retrying (attempt %s) for entity %s due to %s",
            task_name,
            attempt,
            entity_id,
            error_type,
            extra=extra,
        )
    else:
        logger.error(
            "Task %s failed for entity %s: %s",
            task_name,
            entity_id,
            error_type,
            extra=extra,
        )
