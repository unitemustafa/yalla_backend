from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from .models import Order, OrderEvent

User = get_user_model()


ADMIN_STATUS_TRANSITIONS = {
    Order.Status.CONFIRMED: (Order.Status.CANCELLED,),
    Order.Status.ASSIGNED: (Order.Status.CANCELLED,),
    Order.Status.PICKED_UP: (Order.Status.CANCELLED,),
}


def allowed_statuses_for_order(order):
    if order.status in (
        Order.Status.DELIVERED,
        Order.Status.FAILED_DELIVERY,
        Order.Status.CANCELLED,
    ):
        return []
    if order.review_status != Order.ReviewStatus.APPROVED:
        return [Order.Status.CANCELLED] if order.status != Order.Status.CANCELLED else []

    return list(ADMIN_STATUS_TRANSITIONS.get(order.status, ()))


def record_order_event(
    order,
    event_type,
    *,
    actor=None,
    from_status=None,
    to_status=None,
    note="",
    metadata=None,
):
    event_actor = actor if getattr(actor, "is_authenticated", False) else None
    return OrderEvent.objects.create(
        order=order,
        event_type=event_type,
        actor=event_actor,
        from_status=from_status,
        to_status=to_status,
        note=note or "",
        metadata=metadata or {},
    )


def resolve_order_target_user(request, *, action):
    user = request.user
    user_id = request.data.get("user_id")

    if user.role == User.Role.CLIENT:
        if user_id not in (None, "", user.id, str(user.id)):
            raise serializers.ValidationError(
                {
                    "user_id": (
                        f"Client users cannot {action} another customer's order."
                    )
                }
            )
        return user

    if user.role == User.Role.ADMIN or user.is_staff:
        if user_id in (None, ""):
            raise serializers.ValidationError(
                {"user_id": "Select an active client user."}
            )
        try:
            target_user = User.objects.get(pk=int(user_id))
        except (TypeError, ValueError, User.DoesNotExist):
            raise serializers.ValidationError(
                {"user_id": "Select an active client user."}
            )
        if (
            target_user.role != User.Role.CLIENT
            or not target_user.is_active
            or target_user.deleted_at is not None
        ):
            raise serializers.ValidationError(
                {"user_id": "Select an active client user."}
            )
        return target_user

    raise PermissionDenied(f"Only client or admin users can {action} orders.")
