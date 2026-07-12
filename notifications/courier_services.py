from .models import Notification
from .services import create_courier_notification


def _order_number(order):
    return str(getattr(order, "order_number", None) or order.pk)


def notify_courier_order_assigned(order, courier, *, order_event=None):
    number = _order_number(order)
    return create_courier_notification(
        courier,
        notification_type=Notification.Type.ORDER_ASSIGNED,
        title="طلب توصيل جديد",
        message=f"تم تعيين الطلب #{number} لك. اضغط لعرض التفاصيل.",
        order=order,
        order_event=order_event,
        data={"event": "courier_order_assigned", "order_id": str(order.pk),
              "order_number": number, "route": "courier_order_details"},
    )


def notify_courier_order_unassigned(order, courier, *, order_event=None):
    number = _order_number(order)
    return create_courier_notification(
        courier,
        notification_type=Notification.Type.ORDER_UNASSIGNED,
        title="تم سحب طلب",
        message=f"تم سحب الطلب #{number} من قائمة مهامك.",
        order=order,
        order_event=order_event,
        data={"event": "courier_order_unassigned", "order_id": str(order.pk),
              "order_number": number, "route": "courier_orders"},
    )


def notify_courier_order_cancelled(order, courier, *, order_event=None):
    number = _order_number(order)
    return create_courier_notification(
        courier,
        notification_type=Notification.Type.ORDER_CANCELLED,
        title="تم إلغاء طلب",
        message=f"تم إلغاء الطلب #{number}.",
        order=order,
        order_event=order_event,
        data={"event": "courier_order_cancelled", "order_id": str(order.pk),
              "order_number": number, "route": "courier_orders"},
    )
