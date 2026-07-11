from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from markets.models import Market
from offers.models import Offer

from .models import Notification
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


@transaction.atomic
def create_offer_notifications(offer_id):
    offer = (
        Offer.objects.select_for_update()
        .select_related("market")
        .prefetch_related("service_cities", "products__variants")
        .get(pk=offer_id)
    )
    now = timezone.now()
    if (
        offer.status != Offer.Status.ACTIVE
        or offer.start_time > now
        or offer.end_time <= now
        or (offer.market is not None and offer.market.status != Market.Status.ACTIVE)
    ):
        return []

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
            return []
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

    price, price_text = _offer_price(offer)
    image = _offer_image(offer)
    market_name = offer.market.name if offer.market is not None else "Yalla Market"
    created_notification_ids = []
    for batch in _chunks(recipients):
        recipient_ids = [item["id"] for item in batch]
        existing_ids = set(
            Notification.objects.filter(
                recipient_id__in=recipient_ids,
                offer=offer,
                type=Notification.Type.OFFER_CREATED,
            ).values_list("recipient_id", flat=True)
        )
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
                    is_blocking=False,
                    is_resolved=False,
                    data={
                        "event": "offer_created",
                        "action": "open_offer",
                        "offer_id": offer.id,
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
                recipient_id__in=[item.recipient_id for item in objects],
                offer=offer,
                type=Notification.Type.OFFER_CREATED,
            ).values_list("id", flat=True)
        )

    if created_notification_ids:
        transaction.on_commit(
            lambda ids=tuple(created_notification_ids): [
                send_notification_push(notification_id) for notification_id in ids
            ]
        )
    return created_notification_ids
