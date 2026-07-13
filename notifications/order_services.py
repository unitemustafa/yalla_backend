from functools import partial

from django.db import transaction

from orders.models import Order, OrderEvent

from .models import Notification
from .push import send_notification_push


def _content(event_type, order_id, status):
    if event_type == "order_created":
        return "تم استلام طلبك", f"طلبك #{order_id} قيد المراجعة."
    if event_type == "order_review_approved":
        return (
            "تم تأكيد طلبك ✅",
            f"تم قبول طلبك #{order_id} وبدأنا في تجهيزه.",
        )
    if event_type == "order_review_rejected":
        return (
            "تعذر قبول طلبك",
            f"تم رفض طلبك #{order_id}. افتح التطبيق لمعرفة التفاصيل.",
        )
    if event_type == "order_cancelled" or status == Order.Status.CANCELLED:
        return "تم إلغاء الطلب", f"تم إلغاء طلبك #{order_id}."
    if event_type == "order_failed_delivery" or status == Order.Status.FAILED_DELIVERY:
        return (
            "تعذر توصيل الطلب",
            f"تعذر توصيل طلبك #{order_id}. افتح التطبيق لمعرفة التفاصيل.",
        )
    content = {
        Order.Status.CONFIRMED: (
            "تم تأكيد طلبك ✅",
            f"طلبك #{order_id} تم تأكيده.",
        ),
        Order.Status.ASSIGNED: (
            "تم تعيين مندوب لطلبك 🚚",
            f"تم تعيين مندوب لتوصيل طلبك #{order_id}.",
        ),
        Order.Status.PICKED_UP: (
            "تم استلام طلبك من المحلات 📦",
            f"المندوب استلم طلبك #{order_id} من المحلات.",
        ),
        Order.Status.DELIVERED: (
            "تم توصيل طلبك 🎉",
            f"تم توصيل طلبك #{order_id}. نتمنى لك تجربة ممتازة.",
        ),
    }
    return content.get(
        status,
        ("تحديث على طلبك", f"تم تحديث حالة طلبك #{order_id}."),
    )


def _notification_type(event_type):
    return {
        "order_created": Notification.Type.ORDER_CREATED,
        "order_review_approved": Notification.Type.ORDER_REVIEW_APPROVED,
        "order_review_rejected": Notification.Type.ORDER_REJECTED,
        "order_cancelled": Notification.Type.ORDER_CANCELLED,
        "order_failed_delivery": Notification.Type.ORDER_FAILED_DELIVERY,
    }.get(event_type, Notification.Type.ORDER_STATUS_CHANGED)


ADMIN_COURIER_STATUS_EVENTS = {
    Order.Status.PICKED_UP: (
        "courier_order_picked_up",
        "المندوب استلم الطلب",
        "المندوب {courier} استلم الطلب #{order_id} من المحلات.",
    ),
    Order.Status.DELIVERED: (
        "courier_order_delivered",
        "تم تسليم الطلب",
        "المندوب {courier} سلّم الطلب #{order_id} للعميل.",
    ),
}


def create_admin_courier_order_status_notification(order, event, new_status):
    content = ADMIN_COURIER_STATUS_EVENTS.get(new_status)
    if content is None:
        return None

    event_name, title, message_template = content
    courier = order.assigned_representative
    courier_name = (
        courier.get_full_name().strip() or courier.username
        if courier is not None
        else "المندوب"
    )
    notification, _ = Notification.objects.get_or_create(
        audience=Notification.Audience.ADMIN,
        order_event=event,
        defaults={
            "type": Notification.Type.ORDER_STATUS_CHANGED,
            "title": title,
            "message": message_template.format(
                courier=courier_name,
                order_id=order.id,
            ),
            "order": order,
            "is_blocking": False,
            "is_resolved": False,
            "data": {
                "event": event_name,
                "action": "open_order",
                "order_id": order.id,
                "status": new_status,
                "courier_id": courier.id if courier is not None else None,
            },
        },
    )
    return notification


@transaction.atomic
def create_order_lifecycle_notification(
    order_id,
    event_type,
    old_status=None,
    new_status=None,
    order_event_id=None,
):
    try:
        event = OrderEvent.objects.select_related("order").get(
            pk=order_event_id,
            order_id=order_id,
        )
        order = (
            Order.objects.select_related("user", "market")
            .prefetch_related("market_sections__market")
            .get(pk=order_id)
        )
    except (Order.DoesNotExist, OrderEvent.DoesNotExist):
        return None

    recipient = order.user
    if (
        recipient.role != recipient.Role.CLIENT
        or not recipient.is_active
        or recipient.deleted_at is not None
    ):
        return None

    status = new_status or event.to_status or order.status
    old_status = old_status or event.from_status or ""
    title, message = _content(event_type, order.id, status)
    sections = list(order.market_sections.all())
    market_names = []
    for section in sections:
        if section.market.name not in market_names:
            market_names.append(section.market.name)
    if not market_names and order.market_id and order.market.name:
        market_names.append(order.market.name)
    market_count = len(sections) or len(market_names)
    data = {
        "event": event_type,
        "action": "open_order",
        "order_id": order.id,
        "old_status": old_status,
        "status": status,
        "review_status": order.review_status,
        "market_count": market_count,
        "is_multi_market": market_count > 1,
        "market_names_summary": "، ".join(market_names),
    }
    notification, created = Notification.objects.get_or_create(
        recipient=recipient,
        order_event=event,
        defaults={
            "audience": Notification.Audience.CLIENT,
            "type": _notification_type(event_type),
            "title": title,
            "message": message,
            "order": order,
            "is_blocking": False,
            "is_resolved": False,
            "data": data,
        },
    )
    if created:
        transaction.on_commit(partial(send_notification_push, notification.id))
    return notification


def schedule_order_lifecycle_notification(
    order,
    event,
    event_type,
    *,
    old_status=None,
    new_status=None,
):
    transaction.on_commit(
        partial(
            create_order_lifecycle_notification,
            order.id,
            event_type,
            old_status=old_status,
            new_status=new_status,
            order_event_id=event.id,
        )
    )
