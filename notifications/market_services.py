import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from catalog.models import Product
from markets.models import Market

from .models import MarketNotificationDispatch, Notification
from .push import send_notification_push


logger = logging.getLogger(__name__)
User = get_user_model()
BATCH_SIZE = 500


def create_market_notification_intent(market, requested_by_id=None):
    dispatch, _ = MarketNotificationDispatch.objects.get_or_create(
        market=market,
        defaults={"requested_by_id": requested_by_id},
    )
    return dispatch


def schedule_pending_market_notification_for_product(product_id):
    transaction.on_commit(
        lambda current_product_id=product_id: _dispatch_after_commit(
            current_product_id
        )
    )


def _dispatch_after_commit(product_id):
    try:
        dispatch_pending_market_notification_for_product(product_id)
    except Exception:
        logger.exception(
            "Deferred market notification failed for product_id=%s",
            product_id,
        )


def _market_image(market):
    if not market.image:
        return ""
    try:
        return market.image.url
    except ValueError:
        return ""


def _eligible_recipients(market, service_city):
    clients = User.objects.filter(
        role=User.Role.CLIENT,
        is_active=True,
        is_staff=False,
        is_superuser=False,
        deleted_at__isnull=True,
    )
    if market.scope == Market.Scope.GENERAL:
        clients = clients.filter(
            market_region_mode=User.MarketRegionMode.GENERAL,
            market_region_service_city__isnull=True,
        )
    else:
        clients = clients.filter(
            market_region_mode=User.MarketRegionMode.SERVICE_CITY,
            market_region_service_city=service_city,
            market_region_service_city__is_active=True,
        )
    return list(clients.order_by("id").values_list("id", flat=True))


def _create_notifications(dispatch, product, market, recipient_ids, region_name):
    title = f"🏪 محل جديد في {region_name}"
    message = (
        f"محل «{market.name}» اتضاف دلوقتي في {region_name}. "
        "دوس وافتح المحل وشوف منتجاته."
    )
    payload = {
        "event": "market_created",
        "type": "market_created",
        "action": "open_store",
        "market_id": market.id,
        "market_name": market.name,
        "classification_id": market.classification_id,
        "classification_name": market.classification.name,
        "dispatch_id": dispatch.id,
        "trigger_product_id": product.id,
        "region_name": region_name,
        "region_names": [region_name],
        "image": _market_image(market),
    }
    created_ids = []
    for start in range(0, len(recipient_ids), BATCH_SIZE):
        batch = recipient_ids[start : start + BATCH_SIZE]
        existing = set(
            Notification.objects.filter(
                market_dispatch=dispatch,
                recipient_id__in=batch,
            ).values_list("recipient_id", flat=True)
        )
        Notification.objects.bulk_create(
            [
                Notification(
                    recipient_id=recipient_id,
                    audience=Notification.Audience.CLIENT,
                    type=Notification.Type.MARKET_CREATED,
                    title=title,
                    message=message,
                    market_dispatch=dispatch,
                    is_blocking=False,
                    is_resolved=False,
                    data=payload,
                )
                for recipient_id in batch
                if recipient_id not in existing
            ],
            ignore_conflicts=True,
        )
        created_ids.extend(
            Notification.objects.filter(
                market_dispatch=dispatch,
                recipient_id__in=batch,
            ).values_list("id", flat=True)
        )
    return created_ids


def dispatch_pending_market_notification_for_product(product_id):
    created_notification_ids = []
    dispatch = None

    with transaction.atomic():
        product = (
            Product.objects.select_for_update()
            .select_related("market", "market__classification")
            .prefetch_related("market__service_cities", "variants")
            .get(pk=product_id)
        )
        if not product.is_available or not product.variants.exists():
            return None

        dispatch = (
            MarketNotificationDispatch.objects.select_for_update()
            .filter(
                market_id=product.market_id,
                status=MarketNotificationDispatch.Status.PENDING,
            )
            .first()
        )
        if dispatch is None:
            return None

        market = product.market
        if (
            market.status != Market.Status.ACTIVE
            or not market.classification.is_active
        ):
            return None

        service_city = None
        region_name = "السوق العام"
        if market.scope == Market.Scope.SERVICE_CITY:
            active_cities = list(
                market.service_cities.filter(is_active=True).order_by("id")[:2]
            )
            if len(active_cities) != 1:
                return None
            service_city = active_cities[0]
            region_name = service_city.name

        dispatch.status = MarketNotificationDispatch.Status.PROCESSING
        dispatch.trigger_product = product
        dispatch.error_message = ""
        dispatch.save(
            update_fields=["status", "trigger_product", "error_message"]
        )

        recipient_ids = _eligible_recipients(market, service_city)
        created_notification_ids = _create_notifications(
            dispatch,
            product,
            market,
            recipient_ids,
            region_name,
        )
        dispatch.recipient_count = len(recipient_ids)
        dispatch.notification_count = len(created_notification_ids)
        dispatch.status = MarketNotificationDispatch.Status.COMPLETED
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
            send_notification_push(
                notification_id,
                high_priority=True,
                android_channel_id="store_updates",
            )
        except Exception:
            logger.exception(
                "Market-created push failed for notification_id=%s",
                notification_id,
            )
    return dispatch


def completed_market_dispatch_for_product(product_id):
    return (
        MarketNotificationDispatch.objects.filter(
            trigger_product_id=product_id,
            status=MarketNotificationDispatch.Status.COMPLETED,
        )
        .select_related("market")
        .first()
    )
