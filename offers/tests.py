from datetime import timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from catalog.models import CategoryClassification, Product, ProductCategory
from locations.models import ServiceCity
from markets.models import Market, MarketClassification
from orders.models import Order, OrderOffer

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
        market_classification = MarketClassification.objects.create(
            name="مطاعم"
        )
        self.service_city = ServiceCity.objects.create(
            name="Offer City",
            delivery_price=Decimal("100.00"),
        )
        self.remote_city = ServiceCity.objects.create(
            name="Remote Offer City",
            delivery_price=Decimal("120.00"),
        )
        self.client_user.market_region_mode = User.MarketRegionMode.SERVICE_CITY
        self.client_user.market_region_service_city = self.service_city
        self.client_user.market_region_updated_at = timezone.now()
        self.client_user.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )
        self.market = Market.objects.create(
            classification=market_classification,
            name="مطعم العروض",
        )
        self.market.service_cities.add(self.service_city)
        self.other_market = Market.objects.create(
            classification=market_classification,
            name="سوق آخر",
        )
        self.other_market.service_cities.add(self.service_city)
        self.remote_market = Market.objects.create(
            classification=market_classification,
            name="سوق بعيد",
        )
        self.remote_market.service_cities.add(self.remote_city)
        category_classification = CategoryClassification.objects.create(
            name="وجبات"
        )
        self.category = ProductCategory.objects.create(
            classification=category_classification,
            name="وجبات رئيسية",
        )
        self.product = Product.objects.create(
            market=self.market,
            category=self.category,
            name="برغر",
            description="برغر لحم",
        )
        self.second_product = Product.objects.create(
            market=self.market,
            category=self.category,
            name="بطاطا",
            description="بطاطا مقلية",
        )
        self.other_market_product = Product.objects.create(
            market=self.other_market,
            category=self.category,
            name="بيتزا",
            description="بيتزا جبن",
        )
        self.remote_market_product = Product.objects.create(
            market=self.remote_market,
            category=self.category,
            name="سلطة بعيدة",
            description="سلطة",
        )
        self.now = timezone.now()

    def authenticate(self, user):
        refresh = RefreshToken.for_user(user)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )

    def offer_payload(self, **overrides):
        payload = {
            "market_id": self.market.id,
            "scope": Offer.Scope.SERVICE_CITY,
            "service_city_id": self.service_city.id,
            "product_ids": [self.product.id, self.second_product.id],
            "title": " عرض الغداء ",
            "description": " خصم على وجبات الغداء ",
            "type": Offer.OfferType.DISCOUNT,
            "discount": "50.00",
            "start_time": (self.now - timedelta(hours=1)).isoformat(),
            "end_time": (self.now + timedelta(days=1)).isoformat(),
            "active_days": ["saturday", "sunday"],
            "use_limits": 100,
            "user_limit": 2,
            "status": Offer.Status.ACTIVE,
        }
        payload.update(overrides)
        return payload

    def image_file(self, name="offer.gif"):
        return SimpleUploadedFile(
            name,
            (
                b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00"
                b"\xff\xff\xff,\x00\x00\x00\x00\x01\x00\x01\x00"
                b"\x00\x02\x02D\x01\x00;"
            ),
            content_type="image/gif",
        )

    def create_offer(self):
        offer = Offer.objects.create(
            market=self.market,
            scope=Offer.Scope.SERVICE_CITY,
            service_city=self.service_city,
            title="عرض موجود",
            description="وصف العرض",
            type=Offer.OfferType.PACKAGE,
            discount=Decimal("25.00"),
            start_time=self.now - timedelta(hours=1),
            end_time=self.now + timedelta(days=1),
            active_days=["monday"],
            use_limits=20,
            user_limit=1,
            status=Offer.Status.ACTIVE,
        )
        offer.products.set([self.product])
        return offer

    def test_offer_write_requires_admin_role(self):
        self.authenticate(self.client_user)

        response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data["detail"],
            "Only admin users can manage offers.",
        )

    def test_admin_can_create_read_update_and_delete_offer(self):
        self.authenticate(self.admin)

        create_response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(),
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["title"], "عرض الغداء")
        self.assertEqual(create_response.data["market_id"], self.market.id)
        self.assertEqual(create_response.data["market"]["id"], self.market.id)
        self.assertEqual(create_response.data["service_city_id"], self.service_city.id)
        self.assertEqual(
            set(create_response.data["product_ids"]),
            {self.product.id, self.second_product.id},
        )
        self.assertEqual(len(create_response.data["products"]), 2)
        offer_id = create_response.data["id"]

        list_response = self.client.get(f"{OFFERS_BASE}/")
        detail_response = self.client.get(f"{OFFERS_BASE}/{offer_id}/")
        update_response = self.client.patch(
            f"{OFFERS_BASE}/{offer_id}/",
            {
                "title": "عرض العشاء",
                "product_ids": [self.second_product.id],
                "discount": "75.00",
            },
            format="json",
        )
        delete_response = self.client.delete(f"{OFFERS_BASE}/{offer_id}/")
        deleted_detail_response = self.client.get(f"{OFFERS_BASE}/{offer_id}/")

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertIn(offer_id, [item["id"] for item in list_response.data])
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["products"][0]["id"], self.product.id)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["title"], "عرض العشاء")
        self.assertEqual(update_response.data["product_ids"], [self.second_product.id])
        self.assertEqual(update_response.data["products"][0]["id"], self.second_product.id)
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            deleted_detail_response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_offer_create_allows_products_from_same_region_markets(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(product_ids=[self.product.id, self.other_market_product.id]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(
            {product["id"] for product in response.data["products"]},
            {self.product.id, self.other_market_product.id},
        )

    def test_admin_can_create_offer_for_each_model_type_choice(self):
        self.authenticate(self.admin)

        for offer_type, _label in Offer.OfferType.choices:
            response = self.client.post(
                f"{OFFERS_BASE}/",
                self.offer_payload(
                    title=f"عرض {offer_type}",
                    type=offer_type,
                ),
                format="json",
            )

            self.assertEqual(
                response.status_code,
                status.HTTP_201_CREATED,
                response.data,
            )
            self.assertEqual(response.data["type"], offer_type)

    def test_offer_create_rejects_invalid_type(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(type="invalid"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("type", response.data)

    def test_admin_can_create_and_update_offer_image(self):
        self.authenticate(self.admin)

        create_response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(
                active_days='["saturday", "sunday"]',
                image=self.image_file("create.gif"),
            ),
            format="multipart",
        )
        self.assertEqual(
            create_response.status_code,
            status.HTTP_201_CREATED,
            create_response.data,
        )
        offer_id = create_response.data["id"]
        update_response = self.client.patch(
            f"{OFFERS_BASE}/{offer_id}/",
            {"image": self.image_file("update.gif")},
            format="multipart",
        )

        self.assertIsNotNone(create_response.data["image"])
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(update_response.data["image"])

    def test_admin_can_create_general_offer(self):
        general_market = Market.objects.create(
            classification=self.market.classification,
            name="سوق عام",
            scope=Market.Scope.GENERAL,
        )
        general_product = Product.objects.create(
            market=general_market,
            category=self.category,
            name="منتج عام",
            description="متاح عام",
        )
        self.authenticate(self.admin)

        response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(
                market_id=general_market.id,
                scope=Offer.Scope.GENERAL,
                service_city_id=None,
                product_ids=[general_product.id],
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["scope"], Offer.Scope.GENERAL)
        self.assertIsNone(response.data["service_city"])

    def test_offer_create_rejects_products_from_other_region(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(product_ids=[self.product.id, self.remote_market_product.id]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["product_ids"][0],
            "All selected products must belong to the offer region.",
        )

    def test_offer_create_requires_products(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(product_ids=[]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["product_ids"][0],
            "Choose at least one product for this offer.",
        )

    def test_offer_update_rejects_market_change_when_region_does_not_match(self):
        offer = self.create_offer()
        self.authenticate(self.admin)

        response = self.client.patch(
            f"{OFFERS_BASE}/{offer.id}/",
            {"market_id": self.remote_market.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["market_id"][0],
            "Offer market must belong to the selected service city region.",
        )

    def test_client_offer_list_and_detail_are_region_filtered(self):
        visible_offer = self.create_offer()
        hidden_offer = Offer.objects.create(
            market=self.remote_market,
            scope=Offer.Scope.SERVICE_CITY,
            service_city=self.remote_city,
            title="عرض بعيد",
            description="بعيد",
            type=Offer.OfferType.PACKAGE,
            discount=Decimal("10.00"),
            start_time=self.now - timedelta(hours=1),
            end_time=self.now + timedelta(days=1),
            status=Offer.Status.ACTIVE,
        )
        hidden_offer.products.set([self.remote_market_product])
        self.authenticate(self.client_user)

        list_response = self.client.get(f"{OFFERS_BASE}/")
        visible_detail = self.client.get(f"{OFFERS_BASE}/{visible_offer.id}/")
        hidden_detail = self.client.get(f"{OFFERS_BASE}/{hidden_offer.id}/")

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual([offer["id"] for offer in list_response.data], [visible_offer.id])
        self.assertEqual(visible_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(hidden_detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_client_offer_list_requires_saved_market_region(self):
        self.client_user.market_region_mode = None
        self.client_user.market_region_service_city = None
        self.client_user.market_region_updated_at = None
        self.client_user.save(
            update_fields=[
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            ]
        )
        self.authenticate(self.client_user)

        response = self.client.get(f"{OFFERS_BASE}/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data["requires_region_selection"])

    def test_offer_delete_rejects_used_offer(self):
        offer = self.create_offer()
        order = Order.objects.create(
            user=self.client_user,
            market=self.market,
            service_city=self.service_city,
            payment_method="cash",
            discount=Decimal("0.00"),
            description="طلب مرتبط بعرض",
            subtotal_price=Decimal("500.00"),
            total_price=Decimal("600.00"),
        )
        OrderOffer.objects.create(
            order=order,
            offer=offer,
            discount_amount=Decimal("25.00"),
        )
        self.authenticate(self.admin)

        response = self.client.delete(f"{OFFERS_BASE}/{offer.id}/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"],
            "Cannot delete offer while orders are using it.",
        )
