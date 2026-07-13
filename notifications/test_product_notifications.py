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

from .models import Notification, ProductNotificationDispatch

User = get_user_model()
CATALOG_BASE = "/api/v1/catalog"


class ProductNotificationAPITests(APITestCase):
    password = "Password1!"

    def setUp(self):
        self.city = ServiceCity.objects.create(
            name="مدينة المنتج",
            delivery_price=Decimal("25.00"),
        )
        self.other_city = ServiceCity.objects.create(
            name="مدينة تانية",
            delivery_price=Decimal("30.00"),
        )
        classification = MarketClassification.objects.create(name="المحلات")
        self.market = Market.objects.create(
            classification=classification,
            name="محل المدينة",
            scope=Market.Scope.SERVICE_CITY,
        )
        self.market.service_cities.add(self.city)
        self.general_market = Market.objects.create(
            classification=classification,
            name="المحل العام",
            scope=Market.Scope.GENERAL,
        )
        self.general_market.service_cities.add(self.city)
        self.product = Product.objects.create(
            market=self.market,
            name="كشري مخصوص",
            description="كشري جديد",
            is_available=True,
            discount=Decimal("10.00"),
        )
        ProductVariant.objects.create(
            product=self.product,
            price=Decimal("80.00"),
            sku="KOSHARY-1",
        )
        self.general_product = Product.objects.create(
            market=self.general_market,
            name="منتج عام",
            is_available=True,
        )
        ProductVariant.objects.create(
            product=self.general_product,
            price=Decimal("50.00"),
        )

        self.admin = self.create_user(
            "product_notify_admin",
            "+213555910001",
            User.Role.ADMIN,
        )
        self.city_client = self.create_user(
            "product_notify_city",
            "+213555910002",
            User.Role.CLIENT,
            mode=User.MarketRegionMode.SERVICE_CITY,
            city=self.city,
        )
        self.other_city_client = self.create_user(
            "product_notify_other_city",
            "+213555910003",
            User.Role.CLIENT,
            mode=User.MarketRegionMode.SERVICE_CITY,
            city=self.other_city,
        )
        self.general_client = self.create_user(
            "product_notify_general",
            "+213555910004",
            User.Role.CLIENT,
            mode=User.MarketRegionMode.GENERAL,
        )
        self.inactive_client = self.create_user(
            "product_notify_inactive",
            "+213555910005",
            User.Role.CLIENT,
            mode=User.MarketRegionMode.SERVICE_CITY,
            city=self.city,
            is_active=False,
        )

    def create_user(
        self,
        username,
        phone,
        role,
        *,
        mode=None,
        city=None,
        is_active=True,
    ):
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            phone=phone,
            password=self.password,
            role=role,
            is_active=is_active,
            market_region_mode=mode,
            market_region_service_city=city,
            market_region_updated_at=timezone.now() if mode else None,
        )

    def authenticate(self, user):
        refresh = RefreshToken.for_user(user)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )

    def send_notification(self, product, request_id=None):
        return self.client.post(
            f"{CATALOG_BASE}/products/{product.id}/send-notification/",
            {"request_id": request_id or str(uuid.uuid4())},
            format="json",
        )

    @patch("notifications.product_services.send_notification_push")
    def test_service_city_product_notifies_only_clients_who_can_open_it(
        self,
        send_push,
    ):
        self.authenticate(self.admin)
        request_id = str(uuid.uuid4())

        with self.captureOnCommitCallbacks(execute=True):
            first = self.send_notification(self.product, request_id)
        with self.captureOnCommitCallbacks(execute=True):
            repeated = self.send_notification(self.product, request_id)

        self.assertEqual(first.status_code, status.HTTP_200_OK, first.data)
        self.assertEqual(repeated.status_code, status.HTTP_200_OK, repeated.data)
        self.assertEqual(repeated.data["dispatch_id"], first.data["dispatch_id"])
        self.assertEqual(first.data["recipient_count"], 1)
        self.assertEqual(first.data["notification_count"], 1)
        notification = Notification.objects.get(
            product=self.product,
            type=Notification.Type.PRODUCT_CREATED,
        )
        self.assertEqual(notification.recipient, self.city_client)
        self.assertEqual(notification.title, "🛒 منتج جديد وصل يلا ماركت!")
        self.assertEqual(
            notification.message,
            "«كشري مخصوص» متاح دلوقتي من محل المدينة. "
            "دوس وشوف التفاصيل واطلبه بسهولة.",
        )
        self.assertEqual(notification.data["event"], "product_created")
        self.assertEqual(notification.data["action"], "open_product")
        self.assertEqual(notification.data["product_id"], self.product.id)
        self.assertEqual(notification.data["price_text"], "EGP 80")
        self.assertFalse(
            Notification.objects.filter(recipient=self.other_city_client).exists()
        )
        self.assertFalse(
            Notification.objects.filter(recipient=self.general_client).exists()
        )
        self.assertFalse(
            Notification.objects.filter(recipient=self.inactive_client).exists()
        )
        send_push.assert_called_once_with(
            notification.id,
            high_priority=True,
            android_channel_id="product_updates",
        )

    @patch("notifications.product_services.send_notification_push")
    def test_general_product_notifies_general_clients_only(
        self,
        send_push,
    ):
        self.authenticate(self.admin)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.send_notification(self.general_product)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        notifications = Notification.objects.filter(product=self.general_product)
        self.assertEqual(
            set(notifications.values_list("recipient_id", flat=True)),
            {self.general_client.id},
        )
        self.assertEqual(response.data["notification_count"], 1)
        self.assertEqual(send_push.call_count, 1)

    def test_dispatch_rejects_product_without_price(self):
        self.product.variants.all().delete()
        self.authenticate(self.admin)

        response = self.send_notification(self.product)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"],
            "أضف سعرًا واحدًا على الأقل للمنتج قبل إرسال الإشعار.",
        )
        self.assertFalse(Notification.objects.filter(product=self.product).exists())

    def test_product_save_does_not_send_without_explicit_dispatch(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{CATALOG_BASE}/products/",
            {
                "market_id": self.market.id,
                "name": "منتج من غير إشعار",
                "is_available": True,
                "variants": [{"price": "20.00", "selections": []}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertFalse(
            Notification.objects.filter(product_id=response.data["id"]).exists()
        )

    def test_dispatch_rejects_unavailable_product(self):
        self.product.is_available = False
        self.product.save(update_fields=["is_available"])
        self.authenticate(self.admin)

        response = self.send_notification(self.product)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"],
            "خلّي المنتج متاح للبيع الأول علشان تقدر تبعت الإشعار.",
        )
        self.assertFalse(Notification.objects.filter(product=self.product).exists())

    def test_dispatch_rejects_service_market_without_active_city(self):
        self.market.service_cities.clear()
        self.authenticate(self.admin)

        response = self.send_notification(self.product)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Notification.objects.filter(product=self.product).exists())

    def test_dispatch_rejects_inactive_market(self):
        self.market.status = Market.Status.INACTIVE
        self.market.save(update_fields=["status"])
        self.authenticate(self.admin)

        response = self.send_notification(self.product)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"],
            "لا يمكن إرسال الإشعار لأن المحل غير نشط.",
        )
        self.assertFalse(Notification.objects.filter(product=self.product).exists())

    def test_dispatch_requires_admin_role(self):
        self.authenticate(self.city_client)

        response = self.send_notification(self.product)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ProductNotificationDispatch.objects.exists())

    def test_notification_api_exposes_product_id_and_deletion_keeps_history(self):
        self.authenticate(self.admin)
        with self.captureOnCommitCallbacks(execute=False):
            response = self.send_notification(self.product)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        notification = Notification.objects.get(product=self.product)

        self.authenticate(self.city_client)
        list_response = self.client.get("/api/v1/notifications/")
        item = next(
            item for item in list_response.data if item["id"] == notification.id
        )
        self.assertEqual(item["product_id"], self.product.id)

        self.product.delete()
        notification.refresh_from_db()
        dispatch = ProductNotificationDispatch.objects.get(
            pk=response.data["dispatch_id"]
        )
        self.assertIsNone(notification.product_id)
        self.assertIsNone(dispatch.product_id)
