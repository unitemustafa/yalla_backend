from datetime import timedelta
from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import uuid

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from catalog.models import CategoryClassification, Product, ProductCategory, ProductVariant
from locations.models import ServiceCity
from markets.models import Market, MarketClassification
from orders.models import Order, OrderOffer
from notifications.models import Notification

from .models import Offer

User = get_user_model()
OFFERS_BASE = "/api/v1/offers"


class OfferAPITests(APITestCase):
    password = "Password1!"

    def setUp(self):
        self.admin = User.objects.create_user(
            username="offers_admin",
            email="offers-admin@example.com",
            phone="+213555500001",
            password=self.password,
            role=User.Role.ADMIN,
            is_active=True,
        )
        self.client_user = User.objects.create_user(
            username="offers_client",
            email="offers-client@example.com",
            phone="+213555500002",
            password=self.password,
            role=User.Role.CLIENT,
            is_active=True,
        )
        market_classification = MarketClassification.objects.create(name="Markets")
        category_classification = CategoryClassification.objects.create(name="Food")
        self.category = ProductCategory.objects.create(
            classification=category_classification,
            name="Meals",
        )
        self.city = ServiceCity.objects.create(
            name="Offer City",
            delivery_price=Decimal("100.00"),
        )
        self.second_city = ServiceCity.objects.create(
            name="Second City",
            delivery_price=Decimal("110.00"),
        )
        self.remote_city = ServiceCity.objects.create(
            name="Remote City",
            delivery_price=Decimal("120.00"),
        )
        self.inactive_city = ServiceCity.objects.create(
            name="Inactive City",
            delivery_price=Decimal("90.00"),
            is_active=False,
        )
        self.market = Market.objects.create(
            classification=market_classification,
            name="City Market",
        )
        self.market.service_cities.set([self.city, self.second_city])
        self.general_market = Market.objects.create(
            classification=market_classification,
            name="General Market",
            scope=Market.Scope.GENERAL,
        )
        self.general_market.service_cities.set([self.city, self.second_city])
        self.remote_market = Market.objects.create(
            classification=market_classification,
            name="Remote Market",
        )
        self.remote_market.service_cities.set([self.remote_city])
        self.second_market = Market.objects.create(
            classification=market_classification,
            name="Second City Market",
        )
        self.second_market.service_cities.set([self.city])
        self.product = Product.objects.create(
            market=self.market,
            category=self.category,
            name="Burger",
            description="Burger",
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            price=Decimal("100.00"),
            sku="BURGER-SMALL",
        )
        self.second_variant = ProductVariant.objects.create(
            product=self.product,
            price=Decimal("400.00"),
            sku="BURGER-LARGE",
        )
        self.second_product = Product.objects.create(
            market=self.market,
            category=self.category,
            name="Fries",
            description="Fries",
        )
        self.general_product = Product.objects.create(
            market=self.general_market,
            category=self.category,
            name="General Product",
            description="General",
        )
        self.remote_product = Product.objects.create(
            market=self.remote_market,
            category=self.category,
            name="Remote Product",
            description="Remote",
        )
        self.second_market_product = Product.objects.create(
            market=self.second_market,
            category=self.category,
            name="Second Market Product",
            description="Second market",
        )
        self.now = timezone.now()
        self.set_client_region(self.city)

    def authenticate(self, user):
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    def set_client_region(self, city=None):
        if city is None:
            self.client_user.market_region_mode = User.MarketRegionMode.GENERAL
            self.client_user.market_region_service_city = None
        else:
            self.client_user.market_region_mode = User.MarketRegionMode.SERVICE_CITY
            self.client_user.market_region_service_city = city
        self.client_user.market_region_updated_at = timezone.now()
        self.client_user.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )

    def offer_payload(self, **overrides):
        payload = {
            "market_id": self.market.id,
            "show_in_general": False,
            "service_city_ids": [self.city.id],
            "product_ids": [self.product.id],
            "title": " Lunch Offer ",
            "description": " Discount ",
            "type": Offer.OfferType.DISCOUNT,
            "discount": "50.00",
            "start_time": (self.now - timedelta(hours=1)).isoformat(),
            "end_time": (self.now + timedelta(days=1)).isoformat(),
            "active_days": ["saturday", "sunday"],
            "use_limits": 100,
            "user_limit": 2,
            "status": Offer.Status.ACTIVE,
            "send_push_notification": False,
        }
        payload.update(overrides)
        return payload

    def create_offer(self, *, show_in_general=False, cities=None, market=None, product=None):
        offer = Offer.objects.create(
            market=market or self.market,
            show_in_general=show_in_general,
            title="Visible Offer",
            description="Visible",
            type=Offer.OfferType.DISCOUNT,
            discount=Decimal("25.00"),
            start_time=self.now - timedelta(hours=1),
            end_time=self.now + timedelta(days=1),
            status=Offer.Status.ACTIVE,
        )
        offer.products.set([product or self.product])
        offer.service_cities.set(cities or [])
        return offer

    @patch("notifications.offer_services.send_notifications_push")
    def test_city_offer_notifies_only_active_clients_in_selected_city(self, send_push):
        other_city_client = User.objects.create_user(
            username="other_offer_city",
            email="other-offer-city@example.com",
            phone="+213555500020",
            password=self.password,
            role=User.Role.CLIENT,
            market_region_mode=User.MarketRegionMode.SERVICE_CITY,
            market_region_service_city=self.second_city,
        )
        inactive_client = User.objects.create_user(
            username="inactive_offer_city",
            email="inactive-offer-city@example.com",
            phone="+213555500021",
            password=self.password,
            role=User.Role.CLIENT,
            is_active=False,
            market_region_mode=User.MarketRegionMode.SERVICE_CITY,
            market_region_service_city=self.city,
        )
        self.authenticate(self.admin)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"{OFFERS_BASE}/",
                self.offer_payload(send_push_notification=True),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        with self.captureOnCommitCallbacks(execute=True):
            dispatch_response = self.client.post(
                f"{OFFERS_BASE}/{response.data['id']}/send-notification/",
                {"request_id": str(uuid.uuid4())}, format="json",
            )
        self.assertEqual(dispatch_response.status_code, status.HTTP_200_OK, dispatch_response.data)
        notifications = Notification.objects.filter(
            offer_id=response.data["id"],
            type=Notification.Type.OFFER_CREATED,
        )
        self.assertEqual(list(notifications.values_list("recipient_id", flat=True)), [self.client_user.id])
        notification = notifications.get()
        self.assertEqual(notification.data["region_name"], self.city.name)
        self.assertEqual(notification.data["price_text"], "خصم 50%")
        self.assertNotIn(other_city_client.id, notifications.values_list("recipient_id", flat=True))
        self.assertNotIn(inactive_client.id, notifications.values_list("recipient_id", flat=True))
        send_push.assert_called_once_with(
            (notification.id,),
            high_priority=True,
            android_channel_id="offer_updates",
        )

    @patch("notifications.offer_services.send_notifications_push")
    def test_general_offer_notifies_only_general_selected_clients(self, send_push):
        self.set_client_region(None)
        city_client = User.objects.create_user(
            username="city_only_offer",
            email="city-only-offer@example.com",
            phone="+213555500022",
            password=self.password,
            role=User.Role.CLIENT,
            market_region_mode=User.MarketRegionMode.SERVICE_CITY,
            market_region_service_city=self.city,
        )
        self.authenticate(self.admin)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"{OFFERS_BASE}/",
                self.offer_payload(
                    market_id=self.general_market.id,
                    product_ids=[self.general_product.id],
                    show_in_general=True,
                    service_city_ids=[],
                    send_push_notification=True,
                ),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        with self.captureOnCommitCallbacks(execute=True):
            dispatch_response = self.client.post(
                f"{OFFERS_BASE}/{response.data['id']}/send-notification/",
                {"request_id": str(uuid.uuid4())}, format="json",
            )
        self.assertEqual(dispatch_response.status_code, status.HTTP_200_OK, dispatch_response.data)
        notifications = Notification.objects.filter(
            offer_id=response.data["id"],
            type=Notification.Type.OFFER_CREATED,
        )
        self.assertEqual(list(notifications.values_list("recipient_id", flat=True)), [self.client_user.id])
        self.assertNotIn(city_client.id, notifications.values_list("recipient_id", flat=True))
        self.assertEqual(notifications.get().data["region_name"], "السوق العام")
        send_push.assert_called_once()

    def test_inactive_and_future_offers_create_no_immediate_notification(self):
        self.authenticate(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            inactive = self.client.post(
                f"{OFFERS_BASE}/",
                self.offer_payload(status=Offer.Status.INACTIVE),
                format="json",
            )
            future = self.client.post(
                f"{OFFERS_BASE}/",
                self.offer_payload(
                    title="Future",
                    start_time=(self.now + timedelta(hours=1)).isoformat(),
                    end_time=(self.now + timedelta(hours=2)).isoformat(),
                ),
                format="json",
            )
        self.assertEqual(inactive.status_code, status.HTTP_201_CREATED)
        self.assertEqual(future.status_code, status.HTTP_201_CREATED)
        self.assertFalse(
            Notification.objects.filter(
                offer_id__in=[inactive.data["id"], future.data["id"]],
                type=Notification.Type.OFFER_CREATED,
            ).exists()
        )

    def test_admin_can_create_update_list_offer_with_single_city_target(self):
        self.authenticate(self.admin)

        create_response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(service_city_ids=[self.city.id]),
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED, create_response.data)
        self.assertFalse(create_response.data["show_in_general"])
        self.assertEqual(
            create_response.data["service_city_ids"],
            [self.city.id],
        )
        self.assertEqual(len(create_response.data["service_cities"]), 1)
        offer_id = create_response.data["id"]

        update_response = self.client.patch(
            f"{OFFERS_BASE}/{offer_id}/",
            {
                "market_id": self.general_market.id,
                "show_in_general": True,
                "service_city_ids": [],
                "product_ids": [self.general_product.id],
            },
            format="json",
        )
        list_response = self.client.get(f"{OFFERS_BASE}/")

        self.assertEqual(update_response.status_code, status.HTTP_200_OK, update_response.data)
        self.assertTrue(update_response.data["show_in_general"])
        self.assertEqual(update_response.data["service_city_ids"], [])
        self.assertIn(offer_id, [item["id"] for item in list_response.data])

    def test_admin_can_reactivate_expired_offer_by_extending_its_end_time(self):
        self.authenticate(self.admin)
        offer = self.create_offer(cities=[self.city])
        offer.status = Offer.Status.EXPIRED
        offer.end_time = self.now - timedelta(minutes=1)
        offer.save(update_fields=["status", "end_time"])

        response = self.client.patch(
            f"{OFFERS_BASE}/{offer.id}/",
            {"end_time": (self.now + timedelta(days=2)).isoformat()},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["status"], Offer.Status.ACTIVE)

    def test_admin_can_create_each_valid_target_combination(self):
        self.authenticate(self.admin)
        combinations = [
            (False, [self.city.id], self.market.id, [self.product.id]),
            (True, [], self.general_market.id, [self.general_product.id]),
        ]

        for show_in_general, city_ids, market_id, product_ids in combinations:
            response = self.client.post(
                f"{OFFERS_BASE}/",
                self.offer_payload(
                    show_in_general=show_in_general,
                    service_city_ids=city_ids,
                    market_id=market_id,
                    product_ids=product_ids,
                    title=f"Offer {show_in_general} {city_ids}",
                ),
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_offer_create_rejects_general_and_city_targets_together(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(
                show_in_general=True,
                service_city_ids=[self.city.id],
                market_id=self.general_market.id,
                product_ids=[self.general_product.id],
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("show_in_general", response.data)

    def test_offer_create_rejects_multiple_city_targets(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(service_city_ids=[self.city.id, self.second_city.id]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["service_city_ids"][0],
            "Only one service city may be selected.",
        )

    def test_offer_create_rejects_no_target(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(show_in_general=False, service_city_ids=[]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("service_city_ids", response.data)

    def test_offer_create_rejects_inactive_new_city(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(service_city_ids=[self.inactive_city.id]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["service_city_ids"][0],
            "Only active service cities may be selected.",
        )

    def test_offer_create_rejects_unserved_city(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(service_city_ids=[self.remote_city.id]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["service_city_ids"][0],
            "Offer market does not serve every selected city.",
        )

    def test_offer_create_rejects_product_outside_selected_market(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(product_ids=[self.product.id, self.remote_product.id]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["product_ids"][0],
            "العروض غير الباكج يجب أن تكون منتجاتها من محل واحد.",
        )

    def test_service_city_package_accepts_products_from_multiple_markets(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(
                type=Offer.OfferType.PACKAGE,
                product_ids=[self.product.id, self.second_market_product.id],
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(set(response.data["product_ids"]), {self.product.id, self.second_market_product.id})
        self.assertEqual(response.data["market_count"], 2)
        self.assertTrue(response.data["is_multi_market"])
        self.assertEqual(response.data["market_id"], self.market.id)

    def test_offer_create_rejects_missing_products(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(product_ids=[]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("product_ids", response.data)

    def test_admin_offer_items_keep_the_selected_variant_and_quantity(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(
                product_ids=[self.product.id],
                items=[
                    {
                        "variant_id": self.second_variant.id,
                        "quantity": 3,
                        "apply_product_discount": False,
                    }
                ],
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["items"][0]["variant_id"], self.second_variant.id)
        self.assertEqual(response.data["items"][0]["product_id"], self.product.id)
        self.assertEqual(response.data["items"][0]["quantity"], 3)
        self.assertFalse(response.data["items"][0]["apply_product_discount"])
        self.assertEqual(response.data["items"][0]["price"], "400.00")

        offer_id = response.data["id"]
        self.authenticate(self.client_user)
        client_response = self.client.get(f"{OFFERS_BASE}/")

        self.assertEqual(client_response.status_code, status.HTTP_200_OK, client_response.data)
        client_offer = next(item for item in client_response.data if item["id"] == offer_id)
        self.assertEqual(client_offer["products"][0]["offer_variant_id"], self.second_variant.id)
        self.assertEqual(client_offer["products"][0]["offer_quantity"], 3)
        self.assertFalse(client_offer["products"][0]["apply_product_discount"])
        self.assertEqual(client_offer["products"][0]["variants"][0]["id"], self.second_variant.id)

    def test_admin_can_create_all_supported_offer_types(self):
        self.authenticate(self.admin)

        for offer_type in Offer.OfferType.values:
            payload = self.offer_payload(
                type=offer_type,
                title=f"{offer_type} Offer",
            )
            if offer_type == Offer.OfferType.ANNOUNCEMENT:
                payload.update(
                    {
                        "product_ids": [],
                        "announcement_url": "https://example.com/campaign",
                    }
                )
                payload.pop("market_id", None)
            response = self.client.post(
                f"{OFFERS_BASE}/",
                payload,
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
            self.assertEqual(response.data["type"], offer_type)

    def test_admin_can_create_and_update_offer_image_with_multipart_arrays(self):
        self.authenticate(self.admin)

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            image = SimpleUploadedFile(
                "offer.gif",
                b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",
                content_type="image/gif",
            )
            create_response = self.client.post(
                f"{OFFERS_BASE}/",
                {
                    **self.offer_payload(),
                    "service_city_ids": f"[{self.city.id}]",
                    "product_ids": f"[{self.product.id}]",
                    "items": json.dumps(
                        [{"variant_id": self.second_variant.id, "quantity": 2}]
                    ),
                    "active_days": '["saturday","sunday"]',
                    "image": image,
                },
                format="multipart",
            )

            self.assertEqual(create_response.status_code, status.HTTP_201_CREATED, create_response.data)
            self.assertTrue(create_response.data["image"])
            self.assertEqual(
                set(create_response.data["service_city_ids"]),
                {self.city.id},
            )
            self.assertEqual(create_response.data["items"][0]["variant_id"], self.second_variant.id)
            self.assertEqual(create_response.data["items"][0]["quantity"], 2)
            offer_id = create_response.data["id"]

            replacement = SimpleUploadedFile(
                "replacement.gif",
                b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00fff,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",
                content_type="image/gif",
            )
            update_response = self.client.patch(
                f"{OFFERS_BASE}/{offer_id}/",
                {
                    "market_id": self.general_market.id,
                    "show_in_general": "true",
                    "service_city_ids": "[]",
                    "product_ids": f"[{self.general_product.id}]",
                    "image": replacement,
                },
                format="multipart",
            )

            self.assertEqual(update_response.status_code, status.HTTP_200_OK, update_response.data)
            self.assertTrue(update_response.data["show_in_general"])
            self.assertEqual(update_response.data["service_city_ids"], [])
            self.assertTrue(update_response.data["image"])

    def test_admin_delete_rejects_offer_used_by_order(self):
        self.authenticate(self.admin)
        offer = self.create_offer(cities=[self.city])
        order = Order.objects.create(
            user=self.client_user,
            market=self.market,
            service_city=self.city,
            order_scope=Order.Scope.SERVICE_CITY,
            payment_method="cash",
            subtotal_price=Decimal("100.00"),
            total_price=Decimal("100.00"),
        )
        OrderOffer.objects.create(order=order, offer=offer)

        response = self.client.delete(f"{OFFERS_BASE}/{offer.id}/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"],
            "Cannot delete offer while orders are using it.",
        )
        self.assertTrue(Offer.objects.filter(id=offer.id).exists())

    @patch("notifications.offer_services.send_notifications_push")
    def test_push_opt_out_creates_no_notification(self, send_push):
        self.authenticate(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"{OFFERS_BASE}/",
                self.offer_payload(send_push_notification=False),
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(Notification.objects.filter(offer_id=response.data["id"]).exists())
        self.assertIsNone(response.data["push_sent_at"])
        send_push.assert_not_called()

    @patch("notifications.offer_services.send_notifications_push")
    def test_saving_never_sends_and_explicit_request_is_idempotent(self, send_push):
        self.authenticate(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            created = self.client.post(
                f"{OFFERS_BASE}/", self.offer_payload(), format="json"
            )
        offer_url = f"{OFFERS_BASE}/{created.data['id']}/"
        with self.captureOnCommitCallbacks(execute=True):
            enabled = self.client.patch(
                offer_url, {"send_push_notification": True}, format="json"
            )
        with self.captureOnCommitCallbacks(execute=True):
            renamed = self.client.patch(offer_url, {"title": "Renamed"}, format="json")
        self.assertEqual(Notification.objects.filter(offer_id=created.data["id"]).count(), 0)
        send_push.assert_not_called()
        request_id = str(uuid.uuid4())
        with self.captureOnCommitCallbacks(execute=True):
            first = self.client.post(
                f"{offer_url}send-notification/", {"request_id": request_id}, format="json"
            )
        with self.captureOnCommitCallbacks(execute=True):
            repeated = self.client.post(
                f"{offer_url}send-notification/", {"request_id": request_id}, format="json"
            )
        self.assertEqual(first.status_code, status.HTTP_200_OK, first.data)
        self.assertEqual(repeated.data["dispatch_id"], first.data["dispatch_id"])
        offer = Offer.objects.get(pk=created.data["id"])
        self.assertIsNotNone(offer.push_sent_at)
        sent_at = offer.push_sent_at
        offer.refresh_from_db()
        self.assertEqual(offer.push_sent_at, sent_at)
        self.assertEqual(Notification.objects.filter(offer_id=created.data["id"]).count(), 1)
        send_push.assert_called_once()

    @patch("notifications.offer_services.logger")
    @patch(
        "notifications.offer_services.send_notifications_push",
        side_effect=RuntimeError("FCM unavailable"),
    )
    def test_push_failure_does_not_turn_successful_offer_dispatch_into_api_failure(
        self,
        send_push,
        logger,
    ):
        self.authenticate(self.admin)
        created = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(send_push_notification=True),
            format="json",
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"{OFFERS_BASE}/{created.data['id']}/send-notification/",
                {"request_id": str(uuid.uuid4())},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["notification_count"], 1)
        self.assertTrue(
            Notification.objects.filter(offer_id=created.data["id"]).exists()
        )
        send_push.assert_called_once()
        logger.exception.assert_called_once()

    @patch("notifications.offer_services.send_notifications_push")
    def test_expired_offer_can_send_again_after_extending_end_time(self, send_push):
        self.authenticate(self.admin)
        offer = self.create_offer(cities=[self.city])
        offer_url = f"{OFFERS_BASE}/{offer.id}/"

        with self.captureOnCommitCallbacks(execute=True):
            first = self.client.post(
                f"{offer_url}send-notification/",
                {"request_id": str(uuid.uuid4())},
                format="json",
            )
        self.assertEqual(first.status_code, status.HTTP_200_OK, first.data)

        offer.end_time = self.now - timedelta(minutes=1)
        offer.save(update_fields=["end_time"])
        self.assertEqual(offer.get_effective_status(), Offer.Status.EXPIRED)

        extended = self.client.patch(
            offer_url,
            {"end_time": (timezone.now() + timedelta(days=1)).isoformat()},
            format="json",
        )
        self.assertEqual(extended.status_code, status.HTTP_200_OK, extended.data)
        self.assertTrue(extended.data["can_send_notification"])

        with self.captureOnCommitCallbacks(execute=True):
            second = self.client.post(
                f"{offer_url}send-notification/",
                {"request_id": str(uuid.uuid4())},
                format="json",
            )

        self.assertEqual(second.status_code, status.HTTP_200_OK, second.data)
        self.assertNotEqual(second.data["dispatch_id"], first.data["dispatch_id"])
        self.assertEqual(Notification.objects.filter(offer=offer).count(), 2)
        self.assertEqual(send_push.call_count, 2)

    def test_push_sent_at_is_read_only(self):
        self.authenticate(self.admin)
        response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(push_sent_at=(self.now - timedelta(days=1)).isoformat()),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["push_sent_at"])

    def test_send_notification_rejects_non_active_effective_statuses(self):
        self.authenticate(self.admin)
        cases = (
            ("scheduled", self.now + timedelta(hours=1), self.now + timedelta(hours=2), Offer.Status.ACTIVE),
            ("expired", self.now - timedelta(hours=2), self.now - timedelta(hours=1), Offer.Status.ACTIVE),
            ("inactive", self.now - timedelta(hours=1), self.now + timedelta(hours=1), Offer.Status.INACTIVE),
        )
        for label, start_time, end_time, stored_status in cases:
            offer = self.create_offer()
            offer.start_time = start_time
            offer.end_time = end_time
            offer.save(update_fields=["start_time", "end_time", "status"])
            response = self.client.post(
                f"{OFFERS_BASE}/{offer.id}/send-notification/",
                {"request_id": str(uuid.uuid4())}, format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, label)
            self.assertFalse(Notification.objects.filter(offer=offer).exists(), label)

    def test_future_push_offer_is_not_scheduled_or_marked_sent(self):
        self.authenticate(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"{OFFERS_BASE}/",
                self.offer_payload(
                    send_push_notification=True,
                    start_time=(self.now + timedelta(hours=1)).isoformat(),
                    end_time=(self.now + timedelta(hours=2)).isoformat(),
                ),
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["push_sent_at"])
        self.assertFalse(Notification.objects.filter(offer_id=response.data["id"]).exists())

    def test_client_visibility_for_general_and_selected_cities(self):
        city_offer = self.create_offer(cities=[self.city])
        multi_city_offer = self.create_offer(cities=[self.city, self.second_city])
        general_offer = self.create_offer(
            show_in_general=True,
            market=self.general_market,
            product=self.general_product,
        )
        combined_offer = self.create_offer(
            show_in_general=True,
            cities=[self.city],
            market=self.general_market,
            product=self.general_product,
        )
        self.create_offer(cities=[self.remote_city], market=self.remote_market, product=self.remote_product)
        self.authenticate(self.client_user)

        city_response = self.client.get(f"{OFFERS_BASE}/")
        self.set_client_region(self.second_city)
        second_city_response = self.client.get(f"{OFFERS_BASE}/")
        self.set_client_region(self.remote_city)
        remote_city_response = self.client.get(f"{OFFERS_BASE}/")
        self.set_client_region(None)
        general_response = self.client.get(f"{OFFERS_BASE}/")

        self.assertEqual(
            {offer["id"] for offer in city_response.data},
            {city_offer.id, multi_city_offer.id, combined_offer.id},
        )
        self.assertEqual(
            {offer["id"] for offer in second_city_response.data},
            {multi_city_offer.id},
        )
        self.assertNotIn(city_offer.id, {offer["id"] for offer in remote_city_response.data})
        self.assertEqual(
            {offer["id"] for offer in general_response.data},
            {general_offer.id, combined_offer.id},
        )
