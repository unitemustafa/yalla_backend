from django.utils import timezone

from .models import Notification


def create_new_order_review_notification(order):
    return Notification.objects.create(
        audience=Notification.Audience.ADMIN,
        type=Notification.Type.NEW_ORDER_REVIEW,
        title="New order requires review",
        message=f"Order #{order.id} requires admin review.",
        order=order,
        is_blocking=True,
    )


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
