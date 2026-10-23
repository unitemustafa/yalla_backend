"""Run with manage.py shell in the disposable performance container only."""

import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.client_sessions import apply_new_client_session, client_access_token
from accounts.models import CourierProfile, User
from catalog.models import ProductVariant
from locations.models import Address
from orders.models import Order, OrderItem, OrderMarketSection


def seed():
    if not (
        settings.SETTINGS_MODULE == "config.performance_settings"
        and connection.settings_dict["NAME"] == "yalla_perf"
        and connection.settings_dict["HOST"] == "postgres"
    ):
        raise ImproperlyConfigured(
            "Courier seeding requires the isolated performance DB"
        )
    target = Path("/artifacts/accounts.private.json")
    manifest = json.loads(target.read_text(encoding="utf-8"))
    if manifest.get("environment") != "isolated-local-performance":
        raise ValueError("Missing isolated manifest")
    if (
        manifest.get("couriers")
        or User.objects.filter(username__startswith="perf-courier-").exists()
    ):
        raise ValueError("Courier fixtures already exist; refusing to overwrite")
    owner = manifest["accounts"][-1]
    address = Address.objects.get(pk=owner["address_id"], user_id=owner["user_id"])
    catalog = manifest["catalogs"][-1]
    variant = ProductVariant.objects.get(pk=catalog["variant_id"])
    couriers = []
    with transaction.atomic():
        for index in range(20):
            courier = User.objects.create_user(
                username=f"perf-courier-{index:02d}",
                email=f"perf-courier-{index:02d}@example.invalid",
                role=User.Role.REPRESENTATIVE,
            )
            CourierProfile.objects.create(
                user=courier,
                service_city=address.service_city,
                delivery_area=address.delivery_area,
            )
            refresh = RefreshToken.for_user(courier)
            refresh["auth_token_version"] = courier.auth_token_version
            apply_new_client_session(refresh, remember=True)
            orders = Order.objects.bulk_create(
                [
                    Order(
                        user_id=owner["user_id"],
                        market_id=catalog["market_id"],
                        delivery_address=address,
                        service_city=address.service_city,
                        delivery_area=address.delivery_area,
                        order_scope="service_city",
                        delivery_type="fixed_area",
                        fulfillment_type="direct",
                        external_shipping_status="not_required",
                        payment_method="cash",
                        subtotal_price=variant.price,
                        delivery_price=10,
                        total_price=variant.price + 10,
                        status="assigned",
                        review_status="approved",
                        assigned_representative=courier,
                        assigned_at=timezone.now(),
                    )
                    for _ in range(150)
                ]
            )
            sections = OrderMarketSection.objects.bulk_create(
                [
                    OrderMarketSection(
                        order=order,
                        market_id=catalog["market_id"],
                        subtotal_price=variant.price,
                    )
                    for order in orders
                ]
            )
            OrderItem.objects.bulk_create(
                [
                    OrderItem(
                        order=order,
                        section=section,
                        variant=variant,
                        quantity=1,
                        unit_price=variant.price,
                    )
                    for order, section in zip(orders, sections)
                ]
            )
            couriers.append(
                {
                    "user_id": courier.pk,
                    "access": str(client_access_token(refresh)),
                    "refresh": str(refresh),
                    "order_ids": [order.pk for order in orders],
                }
            )
    manifest["couriers"] = couriers
    target.write_text(json.dumps(manifest), encoding="utf-8")
    target.chmod(0o600)
    print(
        "Seeded 20 synthetic couriers and 3000 assigned orders; credentials not printed"
    )


if __name__ == "__main__":
    seed()
