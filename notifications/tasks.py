import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import PushOutbox


logger = logging.getLogger(__name__)


def _delivery_result(entry):
    from .push import (
        _send_account_disabled_event_now,
        _send_account_restored_push_now,
        _send_courier_notification_push_now,
        _send_delivery_area_status_changed_event_now,
        _send_notification_push_now,
    )

    if entry.kind == PushOutbox.Kind.ACCOUNT_DISABLED:
        return _send_account_disabled_event_now(entry.user_id)
    if entry.kind == PushOutbox.Kind.ACCOUNT_RESTORED:
        return _send_account_restored_push_now(entry.notification_id)
    if entry.kind == PushOutbox.Kind.DELIVERY_AREA_STATUS:
        return _send_delivery_area_status_changed_event_now(
            entry.delivery_area_id,
            entry.options["is_active"],
        )
    if entry.kind == PushOutbox.Kind.COURIER_NOTIFICATION:
        return _send_courier_notification_push_now(entry.notification_id)
    return _send_notification_push_now(entry.notification_id, **entry.options)


@shared_task(bind=True, acks_late=True, reject_on_worker_lost=True)
def deliver_push_outbox(self, outbox_id):
    max_attempts = int(getattr(settings, "PUSH_OUTBOX_MAX_ATTEMPTS", 6))
    with transaction.atomic():
        entry = PushOutbox.objects.select_for_update().get(pk=outbox_id)
        if entry.status in {
            PushOutbox.Status.COMPLETED,
            PushOutbox.Status.FAILED,
        }:
            return entry.status
        # Duplicate broker deliveries must not produce duplicate pushes. A
        # processing lease is reclaimed only by the periodic recovery task.
        if entry.status == PushOutbox.Status.PROCESSING:
            return entry.status
        entry.status = PushOutbox.Status.PROCESSING
        entry.attempts += 1
        entry.locked_at = timezone.now()
        entry.save(
            update_fields=["status", "attempts", "locked_at", "updated_at"]
        )

    try:
        result = _delivery_result(entry)
        if result is not None and result.failed_tokens:
            raise RuntimeError(
                f"FCM rejected {len(result.failed_tokens)} active token(s)."
            )
    except Exception as error:
        retry_delay = min(15 * (2 ** max(entry.attempts - 1, 0)), 900)
        terminal = entry.attempts >= max_attempts
        PushOutbox.objects.filter(pk=entry.pk).update(
            status=(
                PushOutbox.Status.FAILED
                if terminal
                else PushOutbox.Status.PENDING
            ),
            available_at=timezone.now() + timedelta(seconds=retry_delay),
            locked_at=None,
            last_error=f"{error.__class__.__name__}: {error}"[:500],
        )
        if terminal:
            logger.exception(
                "push_outbox_permanently_failed outbox_id=%s attempts=%s",
                entry.pk,
                entry.attempts,
            )
            return PushOutbox.Status.FAILED
        raise self.retry(exc=error, countdown=retry_delay)

    PushOutbox.objects.filter(pk=entry.pk).update(
        status=PushOutbox.Status.COMPLETED,
        completed_at=timezone.now(),
        locked_at=None,
        last_error="",
    )
    return PushOutbox.Status.COMPLETED


@shared_task
def publish_pending_push_outbox(batch_size=200):
    cutoff = timezone.now() - timedelta(minutes=15)
    PushOutbox.objects.filter(
        status=PushOutbox.Status.PROCESSING,
        locked_at__lt=cutoff,
    ).update(status=PushOutbox.Status.PENDING, locked_at=None)
    ids = list(
        PushOutbox.objects.filter(
            status=PushOutbox.Status.PENDING,
            available_at__lte=timezone.now(),
        )
        .order_by("available_at")
        .values_list("id", flat=True)[:batch_size]
    )
    for outbox_id in ids:
        deliver_push_outbox.delay(str(outbox_id))
    return len(ids)
