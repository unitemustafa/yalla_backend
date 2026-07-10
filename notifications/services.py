from django.utils import timezone

from accounts.exceptions import ACCOUNT_INACTIVE_MESSAGE

from .models import Notification


def create_account_disabled_notification(user):
    return Notification.objects.create(
        audience=Notification.Audience.CLIENT,
        type=Notification.Type.ACCOUNT_DISABLED,
        title="Account disabled",
        message=ACCOUNT_INACTIVE_MESSAGE,
        recipient=user,
        data={
            "event": "account_disabled",
            "code": "account_inactive",
        },
    )


def create_new_order_review_notification(order):
    notification, _ = Notification.objects.get_or_create(
        order=order,
        audience=Notification.Audience.ADMIN,
        type=Notification.Type.NEW_ORDER_REVIEW,
        is_blocking=True,
        is_resolved=False,
        defaults={
            "title": "New order requires review",
            "message": f"Order #{order.id} requires admin review.",
        },
    )
    return notification


def create_order_assigned_notification(order, representative):
    return Notification.objects.create(
        audience=Notification.Audience.COURIER,
        type=Notification.Type.ORDER_ASSIGNED,
        title="New order assigned",
        message=f"A new order #{order.id} has been assigned to you.",
        order=order,
        recipient=representative,
    )


def create_order_rejected_notification(order):
    return Notification.objects.create(
        audience=Notification.Audience.CLIENT,
        type=Notification.Type.ORDER_REJECTED,
        title="Order rejected",
        message=f"Your order #{order.id} was rejected.",
        order=order,
        recipient=order.user,
    )


def resolve_order_review_notifications(order):
    now = timezone.now()
    return Notification.objects.filter(
        order=order,
        audience=Notification.Audience.ADMIN,
        type=Notification.Type.NEW_ORDER_REVIEW,
        is_blocking=True,
        is_resolved=False,
    ).update(
        is_resolved=True,
        is_read=True,
        resolved_at=now,
        read_at=now,
        updated_at=now,
    )
