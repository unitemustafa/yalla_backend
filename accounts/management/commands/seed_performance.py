"""Provision only the explicitly selected disposable performance database."""

import json
import random
import secrets
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from PIL import Image
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.client_sessions import apply_new_client_session, client_access_token
from accounts.models import User
from catalog.models import Product, ProductVariant, StoreSubcategory
from locations.models import Address, DeliveryArea, ServiceCity
from markets.models import Market, MarketClassification
from notifications.models import Notification
from orders.models import Order


class Command(BaseCommand):
    help = "Seed isolated performance data and write a private load manifest"

    def add_arguments(self, parser):
        parser.add_argument("--output", default="/artifacts/accounts.private.json")
        parser.add_argument("--users", type=int, default=101)
        parser.add_argument("--counts", default="100,1000,10000")
        parser.add_argument("--refresh-tokens", action="store_true")
        parser.add_argument(
            "--reserve-mobile",
            action="store_true",
            help="Add the 101st account to an older 100-account local fixture",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not (
            settings.SETTINGS_MODULE == "config.performance_settings"
            and connection.settings_dict["NAME"] == "yalla_perf"
            and connection.settings_dict["HOST"] == "postgres"
        ):
            raise CommandError(
                "Refusing to seed outside the isolated performance stack"
            )
        if options["reserve_mobile"]:
            output = Path(options["output"])
            manifest = json.loads(output.read_text(encoding="utf-8"))
            if manifest.get("environment") != "isolated-local-performance":
                raise CommandError("Invalid private manifest")
            if len(manifest["accounts"]) == 101:
                self.stdout.write("Separate mobile account already exists")
                return
            if len(manifest["accounts"]) != 100:
                raise CommandError("Expected exactly 100 load accounts")
            template = Address.objects.get(
                pk=manifest["accounts"][-1]["address_id"],
                user__username__startswith="perf-",
            )
            password = secrets.token_urlsafe(24)
            user = User.objects.create_user(
                username="perf-mobile",
                email="perf-mobile@example.invalid",
                password=password,
                terms_accepted=True,
                market_region_mode="service_city",
                market_region_service_city=template.service_city,
                market_region_updated_at=timezone.now(),
            )
            address = Address.objects.create(
                user=user,
                name="PERF mobile home",
                latitude=template.latitude,
                longitude=template.longitude,
                service_city=template.service_city,
                delivery_area=template.delivery_area,
                delivery_type="fixed_area",
                is_default=True,
            )
            refresh = RefreshToken.for_user(user)
            refresh["auth_token_version"] = user.auth_token_version
            apply_new_client_session(refresh, remember=True)
            manifest["accounts"].append(
                {
                    "user_id": user.pk,
                    "email": user.email,
                    "password": password,
                    "access": str(client_access_token(refresh)),
                    "refresh": str(refresh),
                    "address_id": address.pk,
                }
            )
            output.write_text(json.dumps(manifest), encoding="utf-8")
            output.chmod(0o600)
            self.stdout.write(
                "Reserved separate mobile account; no credentials printed"
            )
            return
        if options["refresh_tokens"]:
            output = Path(options["output"])
            manifest = json.loads(output.read_text(encoding="utf-8"))
            if manifest.get("environment") != "isolated-local-performance":
                raise CommandError("Invalid private manifest")
            for account in manifest["accounts"]:
                user = User.objects.get(
                    pk=account["user_id"], username__startswith="perf-"
                )
                refresh = RefreshToken.for_user(user)
                refresh["auth_token_version"] = user.auth_token_version
                apply_new_client_session(refresh, remember=True)
                account.update(
                    access=str(client_access_token(refresh)), refresh=str(refresh)
                )
            output.write_text(json.dumps(manifest), encoding="utf-8")
            output.chmod(0o600)
            self.stdout.write("Private performance credentials renewed")
            return
        counts = [int(n) for n in options["counts"].split(",")]
        if not 1 <= options["users"] <= 101 or any(n < 1 or n > 10000 for n in counts):
            raise CommandError("Users must be 1..101 and catalog sizes 1..10000")
        if User.objects.exists():
            raise CommandError(
                "Database already seeded; preserve it or create a fresh performance volume"
            )
        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
        city = ServiceCity.objects.create(
            name="PERF city",
            center_latitude=36.7525,
            center_longitude=3.042,
            radius_km=20,
            delivery_price=Decimal("10.00"),
        )
        area = DeliveryArea.objects.create(
            name="PERF area",
            service_city=city,
            center_latitude=36.7525,
            center_longitude=3.042,
            radius_km=10,
            delivery_price=Decimal("10.00"),
        )
        classification = MarketClassification.objects.create(name="PERF stores")
        categories = [
            StoreSubcategory.objects.create(name_ar=f"قياس {i}", name_en=f"PERF {i}")
            for i in range(2)
        ]
        media = Path(settings.MEDIA_ROOT) / "performance"
        media.mkdir(parents=True, exist_ok=True)
        images = []
        for i in range(64):
            rng = random.Random(i)
            image = Image.frombytes("RGB", (320, 320), rng.randbytes(320 * 320 * 3))
            stream = BytesIO()
            image.save(stream, format="WEBP", quality=70)
            images.append(stream.getvalue())
        catalogs = []
        for count in counts:
            market = Market.objects.create(
                name=f"PERF {count}", classification=classification
            )
            market.service_cities.add(city)
            market.delivery_areas.add(area)
            market.subcategories.add(*categories)
            products = []
            for i in range(count):
                filename = f"{count}-{i}.webp"
                (media / filename).write_bytes(images[i % len(images)])
                products.append(
                    Product(
                        market=market,
                        subcategory=categories[i % 2],
                        name=f"PERF product {i:05d}",
                        description="منتج قياس صناعي",
                        image=f"performance/{filename}",
                        is_popular=i < 5,
                    )
                )
            Product.objects.bulk_create(products, batch_size=500)
            variants = ProductVariant.objects.bulk_create(
                [
                    ProductVariant(
                        product=p, price=Decimal(10 + i % 90), sku=f"PERF-{count}-{i}"
                    )
                    for i, p in enumerate(products)
                ],
                batch_size=500,
            )
            catalogs.append(
                {
                    "market_id": market.pk,
                    "count": count,
                    "product_id": products[0].pk,
                    "variant_id": variants[0].pk,
                    "subcategory_id": categories[0].pk,
                }
            )
        accounts = []
        password = secrets.token_urlsafe(24)
        for i in range(options["users"]):
            user = User.objects.create_user(
                username=f"perf-{i:03d}",
                email=f"perf-{i:03d}@example.invalid",
                password=password,
                terms_accepted=True,
                market_region_mode="service_city",
                market_region_service_city=city,
                market_region_updated_at=timezone.now(),
            )
            address = Address.objects.create(
                user=user,
                name="PERF home",
                latitude=36.7525,
                longitude=3.042,
                service_city=city,
                delivery_area=area,
                delivery_type="fixed_area",
                is_default=True,
            )
            refresh = RefreshToken.for_user(user)
            refresh["auth_token_version"] = user.auth_token_version
            apply_new_client_session(refresh, remember=True)
            access = client_access_token(refresh)
            # Generated credentials are private artifacts, never stdout/report data.
            accounts.append(
                {
                    "user_id": user.pk,
                    "email": user.email,
                    "password": password,
                    "access": str(access),
                    "refresh": str(refresh),
                    "address_id": address.pk,
                }
            )
            Order.objects.bulk_create(
                [
                    Order(
                        user=user,
                        market_id=catalogs[-1]["market_id"],
                        delivery_address=address,
                        service_city=city,
                        delivery_area=area,
                        order_scope="service_city",
                        delivery_type="fixed_area",
                        payment_method="cash",
                        subtotal_price=10,
                        total_price=20,
                        delivery_price=10,
                        description="PERF historical order",
                    )
                    for _ in range(1000 if i == 0 else 10)
                ]
            )
            if i == 0:
                product_ids = list(
                    Product.objects.filter(
                        market_id=catalogs[-1]["market_id"]
                    ).values_list("id", flat=True)[:1000]
                )
                user.liked_products.add(*product_ids)
                user.liked_markets.add(*[c["market_id"] for c in catalogs])
                Notification.objects.bulk_create(
                    [
                        Notification(
                            recipient=user,
                            title=f"PERF notification {n}",
                            message="Synthetic",
                            audience="client",
                            type="product_created",
                        )
                        for n in range(1000)
                    ]
                )
        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "environment": "isolated-local-performance",
                    "created_at": timezone.now().isoformat(),
                    "expires_at": (timezone.now() + timedelta(hours=7)).isoformat(),
                    "catalogs": catalogs,
                    "accounts": accounts,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        output.chmod(0o600)
        self.stdout.write(
            f"Provisioned {len(accounts)} users and {sum(counts)} products; private manifest written"
        )
