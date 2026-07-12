from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from markets.models import Market
from offers.models import Offer

from rest_framework.exceptions import ValidationError

from .models import Notification, OfferNotificationDispatch
from .push import send_notification_push

User = get_user_model()
BATCH_SIZE = 500


def _trim_decimal(value):
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") or "0"


def _offer_price(offer):
    products = list(offer.products.all())
    if len(products) == 1:
        variants = list(products[0].variants.all())
        if len(variants) == 1 and variants[0].price >= 0:
            price = variants[0].price * (
                Decimal("1") - (offer.discount / Decimal("100"))
            )
            price = max(price, Decimal("0")).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            display = _trim_decimal(price)
            return f"{price:.2f}", f"EGP {display}"
    return None, f"خصم {_trim_decimal(offer.discount)}%"


def _offer_image(offer):
    if not offer.image:
        return ""
    try:
        return offer.image.url
    except ValueError:
        return ""


def _chunks(values):
    for start in range(0, len(values), BATCH_SIZE):
        yield values[start : start + BATCH_SIZE]


def _dispatch_validation_message(offer, now):
    effective_status = offer.get_effective_status(now)
    if effective_status == "scheduled":
        return "لا يمكن إرسال الإشعار قبل بداية العرض."
    if effective_status == Offer.Status.EXPIRED:
        return "لا يمكن إرسال إشعار لعرض منتهي. عدّل توقيت العرض أولًا."
    if effective_status == Offer.Status.INACTIVE:
        return "فعّل العرض أولًا قبل إرسال الإشعار."
    if not offer.has_valid_visibility_scope() or not offer.has_active_markets():
        return "لا يمكن إرسال الإشعار لأن نطاق العرض أو المحلات غير نشط."
    return None


def dispatch_offer_notifications(offer_id, request_id, requested_by_id=None):
    validation_error = None
    with transaction.atomic():
        dispatch, created = OfferNotificationDispatch.objects.get_or_create(
            request_id=request_id,
            defaults={"offer_id": offer_id, "requested_by_id": requested_by_id},
        )
        dispatch = OfferNotificationDispatch.objects.select_for_update().get(pk=dispatch.pk)
        if dispatch.offer_id != offer_id:
            raise ValidationError({"request_id": "This request id belongs to another offer."})
        if not created and dispatch.status == OfferNotificationDispatch.Status.COMPLETED:
            return dispatch

        offer = (
            Offer.objects.select_for_update()
            .select_related("market")
            .prefetch_related("service_cities", "products__variants", "products__market")
            .get(pk=offer_id)
        )
        now = timezone.now()
        validation_error = _dispatch_validation_message(offer, now)
        if validation_error:
            dispatch.status = OfferNotificationDispatch.Status.FAILED
            dispatch.error_message = validation_error
            dispatch.save(update_fields=["status", "error_message"])
        else:
            dispatch.status = OfferNotificationDispatch.Status.PROCESSING
            dispatch.error_message = ""
            dispatch.save(update_fields=["status", "error_message"])

            recipients, region_names = _offer_recipients(offer)
            created_notification_ids = _create_dispatch_notifications(
                offer, dispatch, recipients, region_names
            )
            dispatch.recipient_count = len(recipients)
            dispatch.notification_count = len(created_notification_ids)
            dispatch.status = OfferNotificationDispatch.Status.COMPLETED
            dispatch.completed_at = now
            dispatch.save(update_fields=[
                "recipient_count", "notification_count", "status", "completed_at"
            ])
            Offer.objects.filter(pk=offer.pk).update(push_sent_at=now)
            if created_notification_ids:
                transaction.on_commit(
                    lambda ids=tuple(created_notification_ids): [
                        send_notification_push(notification_id) for notification_id in ids
                    ]
                )

    if validation_error:
        raise ValidationError({"detail": validation_error})
    return dispatch


def _offer_recipients(offer):

    clients = User.objects.filter(
        role=User.Role.CLIENT,
        is_active=True,
        deleted_at__isnull=True,
    )
    if offer.show_in_general:
        recipients = list(
            clients.filter(
                market_region_mode=User.MarketRegionMode.GENERAL,
                market_region_service_city__isnull=True,
            ).values("id")
        )
        region_names = ["السوق العام"]
        for recipient in recipients:
            recipient["region_name"] = "السوق العام"
    else:
        active_cities = list(
            offer.service_cities.filter(is_active=True).values("id", "name")
        )
        if not active_cities:
            return [], []
        city_names = {city["id"]: city["name"] for city in active_cities}
        region_names = list(city_names.values())
        recipients = list(
            clients.filter(
                market_region_mode=User.MarketRegionMode.SERVICE_CITY,
                market_region_service_city_id__in=city_names,
            ).values("id", "market_region_service_city_id")
        )
        for recipient in recipients:
            recipient["region_name"] = city_names[
                recipient["market_region_service_city_id"]
            ]

    return recipients, region_names


def _create_dispatch_notifications(offer, dispatch, recipients, region_names):
    price, price_text = _offer_price(offer)
    image = _offer_image(offer)
    market_name = offer.market.name if offer.market is not None else "Yalla Market"
    created_notification_ids = []
    for batch in _chunks(recipients):
        recipient_ids = [item["id"] for item in batch]
        existing_ids = set(Notification.objects.filter(
            recipient_id__in=recipient_ids, offer_dispatch=dispatch
        ).values_list("recipient_id", flat=True))
        objects = []
        for recipient in batch:
            if recipient["id"] in existing_ids:
                continue
            region_name = recipient["region_name"]
            if offer.show_in_general:
                title = "🔥 عرض جديد متاح الآن"
                message = (
                    f"عرض «{offer.title}» من {market_name} متاح في السوق العام! "
                    f"{price_text} لفترة محدودة، شوفه قبل ما يخلص."
                )
            else:
                title = f"🔥 عرض جديد في {region_name}"
                message = (
                    f"عرض «{offer.title}» من {market_name} وصل {region_name}! "
                    f"{price_text} لفترة محدودة، افتحه قبل ما يفوتك."
                )
            objects.append(
                Notification(
                    recipient_id=recipient["id"],
                    audience=Notification.Audience.CLIENT,
                    type=Notification.Type.OFFER_CREATED,
                    title=title,
                    message=message,
                    offer=offer,
                    offer_dispatch=dispatch,
                    is_blocking=False,
                    is_resolved=False,
                    data={
                        "event": "offer_created",
                        "action": "open_offer",
                        "offer_id": offer.id,
                        "dispatch_id": dispatch.id,
                        "request_id": str(dispatch.request_id),
                        "region_name": region_name,
                        "region_names": region_names,
                        "market_id": offer.market_id,
                        "market_name": market_name,
                        "discount": f"{offer.discount:.2f}",
                        "price": price,
                        "price_text": price_text,
                        "image": image,
                    },
                )
            )
        if not objects:
            continue
        Notification.objects.bulk_create(objects, ignore_conflicts=True)
        created_notification_ids.extend(
            Notification.objects.filter(
                recipient_id__in=[item.recipient_id for item in objects], offer_dispatch=dispatch
            ).values_list("id", flat=True)
        )
    return created_notification_ids


def create_offer_notifications(offer_id):
    """Backward-compatible entry point for the existing offer notification flow."""
    import uuid

    return dispatch_offer_notifications(offer_id, uuid.uuid4())


process_offer_notifications = create_offer_notifications
