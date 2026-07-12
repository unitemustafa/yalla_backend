import logging

from django.db import transaction
from django.utils import timezone

from accounts.exceptions import ACCOUNT_INACTIVE_MESSAGE

from .models import Notification


logger = logging.getLogger(__name__)


def _dispatch_courier_notification(notification_id):
    from .push import send_courier_notification_push

    try:
        send_courier_notification_push(notification_id)
    except Exception:
        logger.exception(
            "Courier notification delivery failed for notification_id=%s",
            notification_id,
        )


def create_courier_notification(
    courier,
    *,
    notification_type,
    title,
    message,
    data,
    order=None,
    order_event=None,
):
    notification = Notification.objects.create(
        audience=Notification.Audience.COURIER,
        type=notification_type,
        title=title,
        message=message,
        recipient=courier,
        order=order,
        order_event=order_event,
        data=data,
    )
    transaction.on_commit(
        lambda notification_id=notification.id: _dispatch_courier_notification(
            notification_id
        )
    )
    return notification

ACCOUNT_RESTORED_TITLE = "تم استعادة حسابك"
ACCOUNT_RESTORED_MESSAGE = "تم استعادة حسابك بواسطة فريق دعم يلا ماركت."


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


def create_account_restored_notification(user):
    Notification.objects.filter(
        recipient=user,
        type=Notification.Type.ACCOUNT_DISABLED,
    ).delete()
    notification = Notification.objects.create(
        audience=Notification.Audience.CLIENT,
        type=Notification.Type.ACCOUNT_RESTORED,
        title=ACCOUNT_RESTORED_TITLE,
        message=ACCOUNT_RESTORED_MESSAGE,
        recipient=user,
        data={
            "event": "account_restored",
            "route": "login",
        },
    )
    transaction.on_commit(
        lambda notification_id=notification.id: _dispatch_account_restored(
            notification_id
        )
    )
    return notification


def _dispatch_account_restored(notification_id):
    from .push import send_account_restored_push

    try:
        send_account_restored_push(notification_id)
    except Exception:
        logger.exception(
            "Account-restored notification delivery failed for "
            "notification_id=%s",
            notification_id,
        )


def create_admin_courier_availability_notification(
    courier,
    *,
    is_available,
    source,
):
    courier_name = courier.get_full_name().strip() or courier.username
    availability_label = "متاح" if is_available else "غير متاح"

    return Notification.objects.create(
        audience=Notification.Audience.ADMIN,
        type=Notification.Type.COURIER_AVAILABILITY_CHANGED,
        title="تحديث حالة المندوب",
        message=f"المندوب {courier_name} أصبح {availability_label}.",
        data={
            "event": "courier_availability_changed",
            "courier_id": str(courier.id),
            "is_available": is_available,
            "source": source,
        },
    )


def create_courier_availability_notification(courier, *, is_available, source):
    availability_label = "متاح" if is_available else "غير متاح"

    return create_courier_notification(
        courier,
        notification_type=Notification.Type.COURIER_AVAILABILITY_CHANGED,
        title="تحديث حالة استقبال الطلبات",
        message=f"تم جعل حالة استقبال الطلبات {availability_label}.",
        data={
            "event": "courier_availability_changed",
            "courier_id": str(courier.id),
            "is_available": is_available,
            "route": "courier_profile",
            "source": source,
        },
    )


def create_courier_password_changed_notification(courier):
    return Notification.objects.create(
        audience=Notification.Audience.COURIER,
        type=Notification.Type.PASSWORD_CHANGED,
        title="تم تغيير كلمة المرور",
        message="تم تغيير كلمة مرور حسابك. سجّل الدخول بكلمة المرور الجديدة.",
        recipient=courier,
        data={
            "event": "password_changed",
            "action": "login",
        },
    )


def create_courier_account_notification(courier, *, restored):
    if restored:
        title = "تم استعادة حسابك"
        message = "تم استعادة حساب المندوب بواسطة فريق دعم يلا ماركت."
        event = "courier_account_restored"
        route = "login"
    else:
        title = "تم تعطيل حسابك"
        message = ACCOUNT_INACTIVE_MESSAGE
        event = "courier_account_disabled"
        route = "login"
    return create_courier_notification(
        courier,
        notification_type=(
            Notification.Type.ACCOUNT_RESTORED
            if restored
            else Notification.Type.ACCOUNT_DISABLED
        ),
        title=title,
        message=message,
        data={"event": event, "route": route, "code": "account_inactive"},
    )


def create_courier_profile_updated_notification(courier):
    return create_courier_notification(
        courier,
        notification_type=Notification.Type.COURIER_PROFILE_UPDATED,
        title="تم تحديث بيانات حسابك",
        message="تم تحديث بيانات المندوب.",
        data={"event": "courier_profile_updated", "route": "courier_profile"},
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
