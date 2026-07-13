import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from locations.models import DeliveryArea

from .models import DeliveryAreaNotificationDispatch, Notification
from .push import send_notification_push


logger = logging.getLogger(__name__)
User = get_user_model()

DELIVERY_AREA_CREATED_TITLE = "وصلنا لمنطقتك"


def _format_decimal(value):
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") or "0"


def schedule_delivery_area_created_notifications(delivery_area_id):
    transaction.on_commit(
        lambda area_id=delivery_area_id: _dispatch_after_commit(area_id)
    )


def _dispatch_after_commit(delivery_area_id):
    try:
        dispatch_delivery_area_created_notifications(delivery_area_id)
    except Exception:
        logger.exception(
            "Delivery-area-created notification dispatch failed for "
            "delivery_area_id=%s",
            delivery_area_id,
        )


def dispatch_delivery_area_created_notifications(delivery_area_id):
    created_notification_ids = []

    with transaction.atomic():
        dispatch, _ = DeliveryAreaNotificationDispatch.objects.get_or_create(
            delivery_area_id=delivery_area_id
        )
        dispatch = DeliveryAreaNotificationDispatch.objects.select_for_update().get(
            pk=dispatch.pk
        )
        if dispatch.status == DeliveryAreaNotificationDispatch.Status.COMPLETED:
            return dispatch

        dispatch.status = DeliveryAreaNotificationDispatch.Status.PROCESSING
        dispatch.save(update_fields=["status"])

        area = DeliveryArea.objects.select_related("service_city").get(
            pk=delivery_area_id
        )
        recipient_ids = list(
            User.objects.filter(
                role=User.Role.CLIENT,
                is_active=True,
                is_staff=False,
                is_superuser=False,
                deleted_at__isnull=True,
                addresses__is_active=True,
                addresses__service_city_id=area.service_city_id,
            )
            .distinct()
            .values_list("id", flat=True)
        )

        fee = _format_decimal(area.delivery_price)
        message = (
            f'تمت إضافة منطقة التوصيل "{area.name}" داخل مدينة '
            f'"{area.service_city.name}". رسوم التوصيل: {fee} جنيه.'
        )
        payload = {
            "event": "delivery_area_created",
            "type": "delivery_area_created",
            "delivery_area_id": area.id,
            "city_id": area.service_city_id,
            "area_name": area.name,
            "city_name": area.service_city.name,
            "delivery_fee": fee,
        }

        for recipient_id in recipient_ids:
            notification, created = Notification.objects.get_or_create(
                delivery_area_dispatch=dispatch,
                recipient_id=recipient_id,
                defaults={
                    "audience": Notification.Audience.CLIENT,
                    "type": Notification.Type.DELIVERY_AREA_CREATED,
                    "title": DELIVERY_AREA_CREATED_TITLE,
                    "message": message,
                    "data": payload,
                },
            )
            if created:
                created_notification_ids.append(notification.id)

        dispatch.recipient_count = len(recipient_ids)
        dispatch.notification_count = Notification.objects.filter(
            delivery_area_dispatch=dispatch
        ).count()
        dispatch.status = DeliveryAreaNotificationDispatch.Status.COMPLETED
        dispatch.completed_at = timezone.now()
        dispatch.save(
            update_fields=[
                "recipient_count",
                "notification_count",
                "status",
                "completed_at",
            ]
        )

    for notification_id in created_notification_ids:
        try:
            send_notification_push(notification_id)
        except Exception:
            logger.exception(
                "Delivery-area-created push failed for notification_id=%s",
                notification_id,
            )

    return dispatch
