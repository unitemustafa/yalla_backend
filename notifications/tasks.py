import logging
import time
from typing import List, Optional

from celery import shared_task
from django.core.exceptions import ObjectDoesNotExist
import requests

from config.celery_utils import calculate_backoff, log_task_execution
from config.redis_client import get_redis_client
from config.firebase_admin import FirebaseConfigurationError

from .models import Notification
from .push import (
    _send_account_disabled_event_now,
    _send_account_restored_push_now,
    _send_courier_notification_push_now,
    _send_delivery_area_status_changed_event_now,
    _send_notification_push_now,
    send_notifications_push,
)

logger = logging.getLogger("notifications.tasks")

RETRYABLE_EXCEPTIONS = (
    requests.exceptions.RequestException,
    ConnectionError,
    TimeoutError,
    OSError,
)


def _mark_push_dispatched(notification_ids):
    for notification in Notification.objects.filter(pk__in=notification_ids).only(
        "id", "data"
    ):
        data = dict(notification.data or {})
        data["push_dispatched"] = True
        Notification.objects.filter(pk=notification.id).update(data=data)


@shared_task(
    bind=True,
    name="notifications.tasks.send_notification_push_task",
    queue="notifications",
    max_retries=4,
    soft_time_limit=10,
    time_limit=15,
)
def send_notification_push_task(
    self,
    notification_id: int,
    *,
    high_priority: bool = False,
    android_channel_id: Optional[str] = None,
):
    """Deliver a push notification asynchronously via Firebase FCM with idempotency & retries."""
    t0 = time.perf_counter()
    attempt = self.request.retries + 1

    # PostgreSQL is the durable source of truth. Redis only provides an atomic
    # short-lived claim that prevents concurrent workers from double-sending.
    dedup_key = f"yalla:push:sent:{notification_id}"
    r = None
    try:
        r = get_redis_client("default")
        val = r.get(dedup_key)
        if val in (b"1", "1", "completed", b"completed"):
            log_task_execution(
                self.name,
                self.request.id,
                notification_id,
                attempt,
                "success",
                (time.perf_counter() - t0) * 1000.0,
            )
            return {"status": "skipped", "reason": "already_sent"}
    except Exception:
        pass

    try:
        notif = (
            Notification.objects.filter(pk=notification_id).only("id", "data").first()
        )
        if not notif:
            return {"status": "skipped", "reason": "does_not_exist"}
        if isinstance(notif.data, dict) and notif.data.get("push_dispatched"):
            if r is not None:
                try:
                    r.set(dedup_key, "completed", ex=86400)
                except Exception:
                    pass
            log_task_execution(
                self.name,
                self.request.id,
                notification_id,
                attempt,
                "success",
                (time.perf_counter() - t0) * 1000.0,
            )
            return {"status": "skipped", "reason": "already_sent"}
    except Exception:
        logger.exception(
            "push_durable_state_check_failed notification_id=%s", notification_id
        )

    # Only one worker may hold the in-flight claim. Retriable failures release it.
    in_flight = False
    if r is not None:
        try:
            claimed = r.set(dedup_key, "processing", ex=30, nx=True)
            if not claimed:
                if r.get(dedup_key) in ("completed", b"completed", "1", b"1"):
                    return {"status": "skipped", "reason": "already_sent"}
                # A worker can be lost while holding the lease. Recheck the
                # durable DB marker after Redis expires before sending again.
                in_flight = True
        except Exception:
            r = None
    if in_flight:
        raise self.retry(countdown=31)

    try:
        result = _send_notification_push_now(
            notification_id,
            high_priority=high_priority,
            android_channel_id=android_channel_id,
        )
        if result and result.failed_tokens:
            raise ConnectionError("Some FCM tokens failed delivery")
        duration_ms = (time.perf_counter() - t0) * 1000.0

        # Persist the durable marker independently from Redis availability.
        try:
            _mark_push_dispatched([notification_id])
        except Exception as exc:
            logger.exception(
                "push_durable_state_update_failed notification_id=%s", notification_id
            )
            raise ConnectionError("Could not persist push delivery state") from exc

        # Redis is an optimization; a failure here must not undo the DB marker.
        if r is not None:
            try:
                r.set(dedup_key, "completed", ex=86400)
            except Exception:
                pass

        log_task_execution(
            self.name,
            self.request.id,
            notification_id,
            attempt,
            "success",
            duration_ms,
        )
        return {
            "status": "success",
            "successful_tokens": len(result.successful_tokens) if result else 0,
            "stale_tokens": len(result.stale_tokens) if result else 0,
            "failed_tokens": len(result.failed_tokens) if result else 0,
        }

    except ObjectDoesNotExist:
        if r is not None:
            try:
                r.delete(dedup_key)
            except Exception:
                pass
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            notification_id,
            attempt,
            "permanent_failure",
            duration_ms,
            error_type="NotificationNotFound",
        )
        return {"status": "skipped", "reason": "does_not_exist"}

    except FirebaseConfigurationError as exc:
        if r is not None:
            try:
                r.delete(dedup_key)
            except Exception:
                pass
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            notification_id,
            attempt,
            "permanent_failure",
            duration_ms,
            error_type="FirebaseConfigurationError",
        )
        return {"status": "failed", "error": str(exc)}

    except RETRYABLE_EXCEPTIONS as exc:
        if r is not None:
            try:
                r.delete(dedup_key)
            except Exception:
                pass
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            notification_id,
            attempt,
            "retry",
            duration_ms,
            error_type=exc.__class__.__name__,
        )
        countdown = calculate_backoff(self.request.retries, base=2.0, max_backoff=60.0)
        raise self.retry(exc=exc, countdown=countdown)

    except Exception as exc:
        if r is not None:
            try:
                r.delete(dedup_key)
            except Exception:
                pass
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            notification_id,
            attempt,
            "permanent_failure",
            duration_ms,
            error_type=exc.__class__.__name__,
        )
        return {"status": "failed", "error": str(exc)}


@shared_task(
    bind=True,
    name="notifications.tasks.send_notifications_multicast_batch_task",
    queue="notifications",
    max_retries=4,
    soft_time_limit=20,
    time_limit=30,
)
def send_notifications_multicast_batch_task(
    self,
    notification_ids: List[int],
    *,
    high_priority: bool = False,
    android_channel_id: Optional[str] = None,
):
    """Deliver a batch of notifications via FCM Multicast in chunks of up to 500."""
    t0 = time.perf_counter()
    attempt = self.request.retries + 1
    batch_count = len(notification_ids)

    try:
        pending_ids = [
            notification.id
            for notification in Notification.objects.filter(
                pk__in=notification_ids
            ).only("id", "data")
            if not (
                isinstance(notification.data, dict)
                and notification.data.get("push_dispatched")
            )
        ]
        if not pending_ids:
            return {"status": "skipped", "reason": "already_sent"}
        result = send_notifications_push(
            pending_ids,
            high_priority=high_priority,
            android_channel_id=android_channel_id,
        )
        dispatched_ids = result.dispatched_notification_ids
        if not result.failed_tokens:
            dispatched_ids = frozenset(pending_ids)
        _mark_push_dispatched(dispatched_ids)
        if result.failed_tokens:
            raise ConnectionError("Some FCM tokens failed delivery")
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            f"batch_{batch_count}",
            attempt,
            "success",
            duration_ms,
        )
        return {
            "status": "success",
            "batch_count": batch_count,
            "successful_tokens": len(result.successful_tokens) if result else 0,
            "stale_tokens": len(result.stale_tokens) if result else 0,
            "failed_tokens": len(result.failed_tokens) if result else 0,
        }

    except FirebaseConfigurationError as exc:
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            f"batch_{batch_count}",
            attempt,
            "permanent_failure",
            duration_ms,
            error_type="FirebaseConfigurationError",
        )
        return {"status": "failed", "error": str(exc)}

    except RETRYABLE_EXCEPTIONS as exc:
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            f"batch_{batch_count}",
            attempt,
            "retry",
            duration_ms,
            error_type=exc.__class__.__name__,
        )
        countdown = calculate_backoff(self.request.retries, base=2.0, max_backoff=60.0)
        raise self.retry(exc=exc, countdown=countdown)

    except Exception as exc:
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            f"batch_{batch_count}",
            attempt,
            "permanent_failure",
            duration_ms,
            error_type=exc.__class__.__name__,
        )
        return {"status": "failed", "error": str(exc)}


@shared_task(
    bind=True,
    name="notifications.tasks.send_courier_notification_push_task",
    queue="notifications",
    max_retries=4,
    soft_time_limit=10,
    time_limit=15,
)
def send_courier_notification_push_task(self, notification_id: int):
    t0 = time.perf_counter()
    attempt = self.request.retries + 1
    try:
        result = _send_courier_notification_push_now(notification_id)
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name, self.request.id, notification_id, attempt, "success", duration_ms
        )
        return {"status": "success"}
    except ObjectDoesNotExist:
        log_task_execution(
            self.name,
            self.request.id,
            notification_id,
            attempt,
            "permanent_failure",
            (time.perf_counter() - t0) * 1000.0,
            error_type="DoesNotExist",
        )
        return {"status": "skipped", "reason": "does_not_exist"}
    except RETRYABLE_EXCEPTIONS as exc:
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            notification_id,
            attempt,
            "retry",
            duration_ms,
            error_type=exc.__class__.__name__,
        )
        countdown = calculate_backoff(self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)
    except Exception as exc:
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            notification_id,
            attempt,
            "permanent_failure",
            duration_ms,
            error_type=exc.__class__.__name__,
        )
        return {"status": "failed", "error": str(exc)}


@shared_task(
    bind=True,
    name="notifications.tasks.send_account_restored_push_task",
    queue="notifications",
    max_retries=4,
    soft_time_limit=10,
    time_limit=15,
)
def send_account_restored_push_task(self, notification_id: int):
    t0 = time.perf_counter()
    attempt = self.request.retries + 1
    try:
        result = _send_account_restored_push_now(notification_id)
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name, self.request.id, notification_id, attempt, "success", duration_ms
        )
        return {"status": "success"}
    except ObjectDoesNotExist:
        log_task_execution(
            self.name,
            self.request.id,
            notification_id,
            attempt,
            "permanent_failure",
            (time.perf_counter() - t0) * 1000.0,
            error_type="DoesNotExist",
        )
        return {"status": "skipped", "reason": "does_not_exist"}
    except RETRYABLE_EXCEPTIONS as exc:
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            notification_id,
            attempt,
            "retry",
            duration_ms,
            error_type=exc.__class__.__name__,
        )
        countdown = calculate_backoff(self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)
    except Exception as exc:
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            notification_id,
            attempt,
            "permanent_failure",
            duration_ms,
            error_type=exc.__class__.__name__,
        )
        return {"status": "failed", "error": str(exc)}


@shared_task(
    bind=True,
    name="notifications.tasks.send_account_disabled_event_task",
    queue="notifications",
    max_retries=4,
    soft_time_limit=10,
    time_limit=15,
)
def send_account_disabled_event_task(self, user_id: int):
    t0 = time.perf_counter()
    attempt = self.request.retries + 1
    try:
        result = _send_account_disabled_event_now(user_id)
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name, self.request.id, user_id, attempt, "success", duration_ms
        )
        return {"status": "success"}
    except RETRYABLE_EXCEPTIONS as exc:
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            user_id,
            attempt,
            "retry",
            duration_ms,
            error_type=exc.__class__.__name__,
        )
        countdown = calculate_backoff(self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)
    except Exception as exc:
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            user_id,
            attempt,
            "permanent_failure",
            duration_ms,
            error_type=exc.__class__.__name__,
        )
        return {"status": "failed", "error": str(exc)}


@shared_task(
    bind=True,
    name="notifications.tasks.send_delivery_area_status_changed_event_task",
    queue="notifications",
    max_retries=4,
    soft_time_limit=10,
    time_limit=15,
)
def send_delivery_area_status_changed_event_task(self, area_id: int, is_active: bool):
    t0 = time.perf_counter()
    attempt = self.request.retries + 1
    try:
        result = _send_delivery_area_status_changed_event_now(area_id, is_active)
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name, self.request.id, area_id, attempt, "success", duration_ms
        )
        return {"status": "success"}
    except RETRYABLE_EXCEPTIONS as exc:
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            area_id,
            attempt,
            "retry",
            duration_ms,
            error_type=exc.__class__.__name__,
        )
        countdown = calculate_backoff(self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)
    except Exception as exc:
        duration_ms = (time.perf_counter() - t0) * 1000.0
        log_task_execution(
            self.name,
            self.request.id,
            area_id,
            attempt,
            "permanent_failure",
            duration_ms,
            error_type=exc.__class__.__name__,
        )
        return {"status": "failed", "error": str(exc)}
