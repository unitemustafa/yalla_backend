from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from catalog.models import CategoryClassification, Product, ProductCategory
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
        self.market = Market.objects.create(
            classification=market_classification,
            name="مطعم العروض",
        )
        self.other_market = Market.objects.create(
            classification=market_classification,
            name="سوق آخر",
        )
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
        self.now = timezone.now()

    def authenticate(self, user):
        refresh = RefreshToken.for_user(user)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}"
        )

    def offer_payload(self, **overrides):
        payload = {
            "market_id": self.market.id,
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

    def create_offer(self):
        offer = Offer.objects.create(
            market=self.market,
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

    def test_offer_crud_requires_admin_role(self):
        self.authenticate(self.client_user)

        response = self.client.get(f"{OFFERS_BASE}/")

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
        self.assertEqual(create_response.data["market"]["id"], self.market.id)
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
        self.assertEqual(update_response.data["products"][0]["id"], self.second_product.id)
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            deleted_detail_response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_offer_create_rejects_products_from_other_market(self):
        self.authenticate(self.admin)

        response = self.client.post(
            f"{OFFERS_BASE}/",
            self.offer_payload(product_ids=[self.product.id, self.other_market_product.id]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["product_ids"][0],
            "All selected products must belong to the offer market.",
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

    def test_offer_update_rejects_market_change_when_products_do_not_match(self):
        offer = self.create_offer()
        self.authenticate(self.admin)

        response = self.client.patch(
            f"{OFFERS_BASE}/{offer.id}/",
            {"market_id": self.other_market.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["product_ids"][0],
            "All selected products must belong to the offer market.",
        )

    def test_offer_delete_rejects_used_offer(self):
        offer = self.create_offer()
        order = Order.objects.create(
            user=self.client_user,
            market=self.market,
            payment_method="cash",
            discount=Decimal("0.00"),
            description="طلب مرتبط بعرض",
            delivery_price=Decimal("100.00"),
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
