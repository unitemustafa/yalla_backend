import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from catalog.models import Product, ProductVariant
from locations.models import ServiceCity
from markets.models import Market, MarketClassification

from .market_services import create_market_notification_intent
from .models import MarketNotificationDispatch, Notification


User = get_user_model()


class MarketNotificationTests(APITestCase):
    password = "Password1!"

    def setUp(self):
        self.city = ServiceCity.objects.create(
            name="مدينة المحل",
            delivery_price=Decimal("20.00"),
        )
        self.other_city = ServiceCity.objects.create(
            name="مدينة أخرى",
            delivery_price=Decimal("30.00"),
        )
        self.classification = MarketClassification.objects.create(
            name="محلات جديدة"
        )
        self.admin = self.create_user("admin", User.Role.ADMIN)
        self.city_client = self.create_user(
            "city",
            User.Role.CLIENT,
            mode=User.MarketRegionMode.SERVICE_CITY,
            city=self.city,
        )
        self.other_city_client = self.create_user(
            "other-city",
            User.Role.CLIENT,
            mode=User.MarketRegionMode.SERVICE_CITY,
            city=self.other_city,
        )
        self.general_client = self.create_user(
            "general",
            User.Role.CLIENT,
            mode=User.MarketRegionMode.GENERAL,
        )

    def create_user(self, suffix, role, *, mode=None, city=None, **extra):
        return User.objects.create_user(
            username=f"market-notify-{suffix}",
            email=f"market-notify-{suffix}@example.com",
            phone=f"+21355592{User.objects.count():04d}",
            password=self.password,
            role=role,
            market_region_mode=mode,
            market_region_service_city=city,
            market_region_updated_at=timezone.now() if mode else None,
            **extra,
        )

    def authenticate(self):
        refresh = RefreshToken.for_user(self.admin)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )

    def make_market(self, scope=Market.Scope.SERVICE_CITY):
        market = Market.objects.create(
            classification=self.classification,
            name="محل الاختبار",
            scope=scope,
        )
        if scope == Market.Scope.SERVICE_CITY:
            market.service_cities.add(self.city)
        return market

    def create_available_product(self, market, name="أول منتج"):
        product = Product.objects.create(
            market=market,
            name=name,
            is_available=True,
        )
        ProductVariant.objects.create(product=product, price=Decimal("25.00"))
        return product

    def test_admin_chooses_per_market_whether_to_queue_notification(self):
        self.authenticate()
        without_notification = self.client.post(
            "/api/v1/home/markets/",
            {
                "classification_id": self.classification.id,
                "name": "من غير إعلان",
                "scope": "general",
                "send_notification": False,
            },
            format="json",
        )
        with_notification = self.client.post(
            "/api/v1/home/markets/",
            {
                "classification_id": self.classification.id,
                "name": "بإعلان مؤجل",
                "scope": "general",
                "send_notification": True,
            },
            format="json",
        )

        self.assertEqual(without_notification.status_code, status.HTTP_201_CREATED)
        self.assertEqual(with_notification.status_code, status.HTTP_201_CREATED)
        self.assertFalse(
            MarketNotificationDispatch.objects.filter(
                market_id=without_notification.data["id"]
            ).exists()
        )
        queued = MarketNotificationDispatch.objects.get(
            market_id=with_notification.data["id"]
        )
        self.assertEqual(queued.status, MarketNotificationDispatch.Status.PENDING)
        self.assertEqual(queued.requested_by, self.admin)

    @patch("notifications.market_services.send_notification_push")
    def test_city_market_waits_for_first_available_product_and_targets_city(
        self,
        send_push,
    ):
        market = self.make_market()
        dispatch = create_market_notification_intent(market, self.admin.id)
        unavailable = Product.objects.create(
            market=market,
            name="غير متاح",
            is_available=False,
        )
        ProductVariant.objects.create(
            product=unavailable,
            price=Decimal("10.00"),
        )

        from .market_services import dispatch_pending_market_notification_for_product

        self.assertIsNone(
            dispatch_pending_market_notification_for_product(unavailable.id)
        )
        product = self.create_available_product(market)
        completed = dispatch_pending_market_notification_for_product(product.id)

        dispatch.refresh_from_db()
        self.assertEqual(completed.id, dispatch.id)
        self.assertEqual(dispatch.status, MarketNotificationDispatch.Status.COMPLETED)
        self.assertEqual(dispatch.trigger_product, product)
        self.assertEqual(dispatch.notification_count, 1)
        notification = Notification.objects.get(market_dispatch=dispatch)
        self.assertEqual(notification.recipient, self.city_client)
        self.assertEqual(notification.data["action"], "open_store")
        self.assertEqual(notification.data["market_id"], market.id)
        self.assertFalse(
            Notification.objects.filter(recipient=self.other_city_client).exists()
        )
        self.assertFalse(
            Notification.objects.filter(recipient=self.general_client).exists()
        )
        send_push.assert_called_once_with(
            notification.id,
            high_priority=True,
            android_channel_id="store_updates",
        )

    def test_general_market_targets_general_clients_only(self):
        market = self.make_market(Market.Scope.GENERAL)
        dispatch = create_market_notification_intent(market, self.admin.id)
        product = self.create_available_product(market)

        from .market_services import dispatch_pending_market_notification_for_product

        dispatch_pending_market_notification_for_product(product.id)

        self.assertEqual(
            set(
                Notification.objects.filter(market_dispatch=dispatch).values_list(
                    "recipient_id", flat=True
                )
            ),
            {self.general_client.id},
        )

    def test_second_product_does_not_duplicate_market_announcement(self):
        market = self.make_market()
        dispatch = create_market_notification_intent(market, self.admin.id)
        first = self.create_available_product(market, "الأول")
        second = self.create_available_product(market, "الثاني")

        from .market_services import dispatch_pending_market_notification_for_product

        dispatch_pending_market_notification_for_product(first.id)
        self.assertIsNone(
            dispatch_pending_market_notification_for_product(second.id)
        )
        self.assertEqual(
            Notification.objects.filter(market_dispatch=dispatch).count(),
            1,
        )

    def test_product_notification_is_suppressed_after_market_announcement(self):
        market = self.make_market()
        market_dispatch = create_market_notification_intent(market, self.admin.id)
        product = self.create_available_product(market)
        from .market_services import dispatch_pending_market_notification_for_product

        dispatch_pending_market_notification_for_product(product.id)
        self.authenticate()

        response = self.client.post(
            f"/api/v1/catalog/products/{product.id}/send-notification/",
            {"request_id": str(uuid.uuid4())},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data["suppressed_by_market_notification"])
        self.assertEqual(response.data["dispatch_id"], market_dispatch.id)
        self.assertFalse(
            Notification.objects.filter(
                type=Notification.Type.PRODUCT_CREATED,
                product=product,
            ).exists()
        )

    @patch(
        "notifications.market_services.send_notification_push",
        side_effect=RuntimeError("firebase unavailable"),
    )
    def test_product_create_triggers_pending_announcement_without_failing_save(
        self,
        _send_push,
    ):
        market = self.make_market()
        dispatch = create_market_notification_intent(market, self.admin.id)
        self.authenticate()

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/v1/catalog/products/",
                {
                    "market_id": market.id,
                    "name": "منتج يفعّل الإعلان",
                    "is_available": True,
                    "variants": [{"price": "35.00", "selections": []}],
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        dispatch.refresh_from_db()
        self.assertEqual(dispatch.status, MarketNotificationDispatch.Status.COMPLETED)
        self.assertEqual(dispatch.trigger_product_id, response.data["id"])
        self.assertEqual(dispatch.notification_count, 1)
