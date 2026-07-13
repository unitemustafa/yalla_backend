from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import Product
from markets.models import Market

from .models import Notification, ProductNotificationDispatch
from .push import send_notification_push

User = get_user_model()
BATCH_SIZE = 500


def _trim_decimal(value):
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") or "0"


def _product_price(product):
    prices = [variant.price for variant in product.variants.all()]
    if not prices:
        return None, ""
    price = min(prices).quantize(Decimal("0.01"))
    display = _trim_decimal(price)
    return f"{price:.2f}", f"EGP {display}"


def _product_image(product):
    if product.image:
        try:
            return product.image.url
        except ValueError:
            pass

    images = list(product.images.all())
    primary = next((image for image in images if image.is_primary), None)
    selected = primary or (images[0] if images else None)
    if selected is None:
        return ""
    try:
        return selected.image.url
    except ValueError:
        return ""


def _chunks(values):
    for start in range(0, len(values), BATCH_SIZE):
        yield values[start : start + BATCH_SIZE]


def _active_market_cities(market):
    return {
        city["id"]: city["name"]
        for city in market.service_cities.filter(is_active=True).values("id", "name")
    }


def _dispatch_validation_message(product):
    if not product.is_available:
        return "خلّي المنتج متاح للبيع الأول علشان تقدر تبعت الإشعار."
    if not product.variants.exists():
        return "أضف سعرًا واحدًا على الأقل للمنتج قبل إرسال الإشعار."
    if product.market.status != Market.Status.ACTIVE:
        return "لا يمكن إرسال الإشعار لأن المحل غير نشط."
    if (
        product.market.scope == Market.Scope.SERVICE_CITY
        and not _active_market_cities(product.market)
    ):
        return "لا يمكن إرسال الإشعار لأن المحل مش مرتبط بمدينة خدمة نشطة."
    return None


def _product_recipients(product):
    market = product.market
    active_cities = _active_market_cities(market)
    clients = User.objects.filter(
        role=User.Role.CLIENT,
        is_active=True,
        is_staff=False,
        is_superuser=False,
        deleted_at__isnull=True,
    )

    if market.scope == Market.Scope.GENERAL:
        audience = Q(market_region_mode=User.MarketRegionMode.GENERAL)
    else:
        audience = Q(
            market_region_mode=User.MarketRegionMode.SERVICE_CITY,
            market_region_service_city_id__in=active_cities,
            market_region_service_city__is_active=True,
        )

    recipients = list(
        clients.filter(audience)
        .values(
            "id",
            "market_region_mode",
            "market_region_service_city_id",
        )
        .order_by("id")
    )
    for recipient in recipients:
        city_id = recipient["market_region_service_city_id"]
        recipient["region_name"] = (
            active_cities.get(city_id, "السوق العام")
            if recipient["market_region_mode"]
            == User.MarketRegionMode.SERVICE_CITY
            else "السوق العام"
        )
    return recipients, list(active_cities.values())


def _create_dispatch_notifications(product, dispatch, recipients, region_names):
    market_name = product.market.name or "يلا ماركت"
    price, price_text = _product_price(product)
    image = _product_image(product)
    title = "🛒 منتج جديد وصل يلا ماركت!"
    message = (
        f"«{product.name}» متاح دلوقتي من {market_name}. "
        "دوس وشوف التفاصيل واطلبه بسهولة."
    )
    created_notification_ids = []

    for batch in _chunks(recipients):
        recipient_ids = [recipient["id"] for recipient in batch]
        existing_ids = set(
            Notification.objects.filter(
                recipient_id__in=recipient_ids,
                product_dispatch=dispatch,
            ).values_list("recipient_id", flat=True)
        )
        notifications = []
        for recipient in batch:
            if recipient["id"] in existing_ids:
                continue
            notifications.append(
                Notification(
                    recipient_id=recipient["id"],
                    audience=Notification.Audience.CLIENT,
                    type=Notification.Type.PRODUCT_CREATED,
                    title=title,
                    message=message,
                    product=product,
                    product_dispatch=dispatch,
                    is_blocking=False,
                    is_resolved=False,
                    data={
                        "event": "product_created",
                        "action": "open_product",
                        "product_id": product.id,
                        "product_name": product.name,
                        "dispatch_id": dispatch.id,
                        "request_id": str(dispatch.request_id),
                        "region_name": recipient["region_name"],
                        "region_names": region_names,
                        "market_id": product.market_id,
                        "market_name": market_name,
                        "discount": f"{product.discount:.2f}",
                        "price": price,
                        "price_text": price_text,
                        "image": image,
                    },
                )
            )

        if not notifications:
            continue
        Notification.objects.bulk_create(notifications, ignore_conflicts=True)
        created_notification_ids.extend(
            Notification.objects.filter(
                recipient_id__in=[item.recipient_id for item in notifications],
                product_dispatch=dispatch,
            ).values_list("id", flat=True)
        )

    return created_notification_ids


def dispatch_product_notifications(product_id, request_id, requested_by_id=None):
    validation_error = None

    with transaction.atomic():
        dispatch, created = ProductNotificationDispatch.objects.get_or_create(
            request_id=request_id,
            defaults={
                "product_id": product_id,
                "requested_by_id": requested_by_id,
            },
        )
        dispatch = ProductNotificationDispatch.objects.select_for_update().get(
            pk=dispatch.pk
        )
        if dispatch.product_id != product_id:
            raise ValidationError(
                {"request_id": "This request id belongs to another product."}
            )
        if not created and dispatch.status == ProductNotificationDispatch.Status.COMPLETED:
            return dispatch

        product = (
            Product.objects.select_for_update()
            .select_related("market")
            .prefetch_related("market__service_cities", "variants", "images")
            .get(pk=product_id)
        )
        validation_error = _dispatch_validation_message(product)
        if validation_error:
            dispatch.status = ProductNotificationDispatch.Status.FAILED
            dispatch.error_message = validation_error
            dispatch.save(update_fields=["status", "error_message"])
        else:
            dispatch.status = ProductNotificationDispatch.Status.PROCESSING
            dispatch.error_message = ""
            dispatch.save(update_fields=["status", "error_message"])

            recipients, region_names = _product_recipients(product)
            created_notification_ids = _create_dispatch_notifications(
                product,
                dispatch,
                recipients,
                region_names,
            )
            now = timezone.now()
            dispatch.recipient_count = len(recipients)
            dispatch.notification_count = len(created_notification_ids)
            dispatch.status = ProductNotificationDispatch.Status.COMPLETED
            dispatch.completed_at = now
            dispatch.save(
                update_fields=[
                    "recipient_count",
                    "notification_count",
                    "status",
                    "completed_at",
                ]
            )
            if created_notification_ids:
                transaction.on_commit(
                    lambda ids=tuple(created_notification_ids): [
                        send_notification_push(
                            notification_id,
                            high_priority=True,
                            android_channel_id="product_updates",
                        )
                        for notification_id in ids
                    ]
                )

    if validation_error:
        raise ValidationError({"detail": validation_error})
    return dispatch
