import logging

from django.db import transaction

from .models import PushOutbox


logger = logging.getLogger(__name__)


def _publish(outbox_id):
    from .tasks import deliver_push_outbox

    try:
        deliver_push_outbox.delay(str(outbox_id))
    except Exception:
        logger.exception(
            "push_outbox_publish_failed outbox_id=%s",
            outbox_id,
        )


def enqueue_notification_push(
    notification_id,
    *,
    kind=PushOutbox.Kind.NOTIFICATION,
    high_priority=False,
    android_channel_id=None,
):
    entry = PushOutbox.objects.create(
        kind=kind,
        notification_id=notification_id,
        options={
            "high_priority": bool(high_priority),
            "android_channel_id": android_channel_id,
        },
    )
    transaction.on_commit(
        lambda entry_id=entry.id: _publish(entry_id),
        robust=True,
    )
    return entry


def enqueue_account_disabled_push(user_id):
    entry = PushOutbox.objects.create(
        kind=PushOutbox.Kind.ACCOUNT_DISABLED,
        user_id=user_id,
    )
    transaction.on_commit(
        lambda entry_id=entry.id: _publish(entry_id),
        robust=True,
    )
    return entry


def enqueue_delivery_area_status_push(area_id, is_active):
    entry = PushOutbox.objects.create(
        kind=PushOutbox.Kind.DELIVERY_AREA_STATUS,
        delivery_area_id=area_id,
        options={"is_active": bool(is_active)},
    )
    transaction.on_commit(
        lambda entry_id=entry.id: _publish(entry_id),
        robust=True,
    )
    return entry
