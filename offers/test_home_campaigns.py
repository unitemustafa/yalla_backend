from datetime import timedelta
from decimal import Decimal
import base64
import struct
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from catalog.models import (
    CategoryClassification,
    Product,
    ProductCategory,
    ProductVariant,
    StoreSubcategory,
)
from locations.models import ServiceCity
from markets.models import Market, MarketClassification
from .models import HomeCampaign


User = get_user_model()
CAMPAIGNS_BASE = "/api/v1/offers/home-campaigns/"


def _atom(atom_type, payload):
    return struct.pack(">I4s", len(payload) + 8, atom_type) + payload


def mp4_upload(seconds=5):
    mvhd = (
        b"\x00\x00\x00\x00"
        + b"\x00" * 8
        + struct.pack(">I", 1000)
        + struct.pack(">I", seconds * 1000)
    )
    content = _atom(b"ftyp", b"isom\x00\x00\x02\x00isom") + _atom(
        b"moov", _atom(b"mvhd", mvhd)
    )
    return SimpleUploadedFile("campaign.mp4", content, content_type="video/mp4")


def image_upload(name="campaign.png"):
    content = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    return SimpleUploadedFile(name, content, content_type="image/png")


class HomeCampaignAPITests(APITestCase):
    password = "Password1!"

    def setUp(self):
        self.now = timezone.now()
        self.admin = User.objects.create_user(
            username="campaign_admin",
            email="campaign-admin@example.com",
            phone="+201000000401",
            password=self.password,
            role=User.Role.ADMIN,
        )
        self.user = User.objects.create_user(
            username="campaign_client",
            email="campaign-client@example.com",
            phone="+201000000402",
            password=self.password,
            role=User.Role.CLIENT,
        )
        self.city = ServiceCity.objects.create(
            name="Campaign City",
            delivery_price=Decimal("25.00"),
        )
        self.user.market_region_mode = User.MarketRegionMode.SERVICE_CITY
        self.user.market_region_service_city = self.city
        self.user.market_region_updated_at = self.now
        self.user.save(
            update_fields=(
                "market_region_mode",
                "market_region_service_city",
                "market_region_updated_at",
            )
        )
        market_classification = MarketClassification.objects.create(name="Campaign Shops")
        self.market = Market.objects.create(
            classification=market_classification,
            name="Campaign Market",
        )
        self.market.service_cities.add(self.city)
        category_classification = CategoryClassification.objects.create(name="Campaign Food")
        self.category = ProductCategory.objects.create(
            classification=category_classification,
            name="Campaign Meals",
        )
        self.subcategory = StoreSubcategory.objects.create(
            name_ar="حملات",
            name_en="Campaigns",
        )
        self.market.subcategories.add(self.subcategory)
        self.product = Product.objects.create(
            market=self.market,
            category=self.category,
            subcategory=self.subcategory,
            name="Campaign Product",
        )
        ProductVariant.objects.create(
            product=self.product,
            price=Decimal("100.00"),
            sku="CAMPAIGN-1",
        )

    def authenticate(self, user):
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    def payload(self, **overrides):
        payload = {
            "internal_name": "First order campaign",
            "is_active": True,
            "start_time": (self.now - timedelta(hours=1)).isoformat(),
            "end_time": (self.now + timedelta(days=2)).isoformat(),
            "show_in_general": False,
            "service_city_id": self.city.id,
            "teaser_text": "توصيل مجاني على أول طلب",
            "title": "توصيل مجاني",
            "description": "اطلب الآن واستمتع بالتوصيل المجاني.",
            "template": HomeCampaign.Template.HERO,
            "sheet_size": HomeCampaign.SheetSize.LARGE,
            "content_alignment": HomeCampaign.Alignment.CENTER,
            "use_theme_colors": True,
            "media_type": HomeCampaign.MediaType.NONE,
            "open_mode": HomeCampaign.OpenMode.TAP_ONLY,
            "dismiss_behavior": HomeCampaign.DismissBehavior.COLLAPSE_ONLY,
            "action_type": HomeCampaign.ActionType.NONE,
            "cta_label": "",
        }
        payload.update(overrides)
        return payload

    def create_campaign(self, **overrides):
        return HomeCampaign.objects.create(
            internal_name=overrides.pop("internal_name", "Campaign"),
            is_active=overrides.pop("is_active", True),
            start_time=overrides.pop("start_time", self.now - timedelta(hours=1)),
            end_time=overrides.pop("end_time", self.now + timedelta(days=2)),
            show_in_general=overrides.pop("show_in_general", False),
            service_city=overrides.pop("service_city", self.city),
            teaser_text=overrides.pop("teaser_text", "شريط الحملة"),
            title=overrides.pop("title", "عنوان الحملة"),
            description=overrides.pop("description", "وصف الحملة"),
            media_type=overrides.pop("media_type", HomeCampaign.MediaType.NONE),
            action_type=overrides.pop("action_type", HomeCampaign.ActionType.NONE),
            **overrides,
        )

    def test_admin_can_create_list_update_and_delete_campaign(self):
        self.authenticate(self.admin)
        created = self.client.post(CAMPAIGNS_BASE, self.payload(), format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        campaign_id = created.data["id"]
        self.assertEqual(created.data["effective_status"], "active")

        listed = self.client.get(CAMPAIGNS_BASE)
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        results = listed.data.get("results", []) if isinstance(listed.data, dict) else listed.data
        self.assertEqual(results[0]["id"], campaign_id)

        updated = self.client.patch(
            f"{CAMPAIGNS_BASE}{campaign_id}/",
            {"use_theme_colors": False},
            format="json",
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertFalse(updated.data["use_theme_colors"])
        self.assertNotIn("priority", updated.data)
        self.assertNotIn("audience", updated.data)

        deleted = self.client.delete(f"{CAMPAIGNS_BASE}{campaign_id}/")
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(HomeCampaign.objects.filter(pk=campaign_id).exists())

    def test_action_requires_matching_target_and_https_url(self):
        self.authenticate(self.admin)
        missing_product = self.client.post(
            CAMPAIGNS_BASE,
            self.payload(
                action_type=HomeCampaign.ActionType.PRODUCT,
                cta_label="اطلب الآن",
            ),
            format="json",
        )
        self.assertEqual(missing_product.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("target_product_id", missing_product.data)

        insecure_url = self.client.post(
            CAMPAIGNS_BASE,
            self.payload(
                action_type=HomeCampaign.ActionType.EXTERNAL_URL,
                cta_label="افتح الرابط",
                external_url="http://example.com",
            ),
            format="json",
        )
        self.assertEqual(insecure_url.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("external_url", insecure_url.data)

    def test_home_returns_one_eligible_campaign_with_theme_color_mode(self):
        selected = self.create_campaign(
            internal_name="Selected",
            teaser_text="الحملة",
            action_type=HomeCampaign.ActionType.PRODUCT,
            target_product=self.product,
            cta_label="افتح المنتج",
        )
        self.authenticate(self.user)

        response = self.client.get("/api/v1/home/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["home_campaign"]["id"], selected.id)
        self.assertEqual(response.data["home_campaign"]["teaser"]["text"], "الحملة")
        self.assertTrue(response.data["home_campaign"]["sheet"]["use_theme_colors"])
        self.assertEqual(
            response.data["home_campaign"]["action"]["target"]["id"],
            self.product.id,
        )

    @override_settings(HOME_CAMPAIGN_ROTATION_MINUTES=30)
    def test_eligible_campaigns_rotate_every_thirty_minutes(self):
        first = self.create_campaign(internal_name="First")
        second = self.create_campaign(internal_name="Second")
        self.authenticate(self.user)

        with patch("offers.campaign_services.timezone.now", return_value=self.now):
            initial_response = self.client.get("/api/v1/home/")
        with patch(
            "offers.campaign_services.timezone.now",
            return_value=self.now + timedelta(minutes=30),
        ):
            rotated_response = self.client.get("/api/v1/home/")
        with patch(
            "offers.campaign_services.timezone.now",
            return_value=self.now + timedelta(minutes=60),
        ):
            repeated_response = self.client.get("/api/v1/home/")

        first_id = initial_response.data["home_campaign"]["id"]
        self.assertIn(first_id, {first.id, second.id})
        self.assertNotEqual(rotated_response.data["home_campaign"]["id"], first_id)
        self.assertEqual(repeated_response.data["home_campaign"]["id"], first_id)

    def test_schedule_and_city_scope_exclude_campaigns(self):
        other_city = ServiceCity.objects.create(
            name="Other Campaign City",
            delivery_price=Decimal("25.00"),
        )
        self.create_campaign(service_city=other_city)
        self.create_campaign(
            start_time=self.now + timedelta(hours=1),
            end_time=self.now + timedelta(days=2),
        )
        self.create_campaign(
            start_time=self.now - timedelta(days=2),
            end_time=self.now - timedelta(hours=1),
        )
        self.authenticate(self.user)

        response = self.client.get("/api/v1/home/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["home_campaign"])

    def test_unavailable_internal_target_is_skipped(self):
        self.create_campaign(
            action_type=HomeCampaign.ActionType.PRODUCT,
            target_product=self.product,
            cta_label="افتح المنتج",
        )
        self.product.is_available = False
        self.product.save(update_fields=("is_available",))
        self.authenticate(self.user)

        response = self.client.get("/api/v1/home/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["home_campaign"])

    def test_video_upload_rejects_duration_over_thirty_seconds(self):
        campaign = self.create_campaign(is_active=False)
        self.authenticate(self.admin)

        response = self.client.post(
            f"{CAMPAIGNS_BASE}{campaign.id}/media/",
            {"video": mp4_upload(seconds=31)},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("video", response.data)

    def test_video_requires_poster_before_activation(self):
        campaign = self.create_campaign(
            is_active=False,
            media_type=HomeCampaign.MediaType.VIDEO,
        )
        self.authenticate(self.admin)
        uploaded = self.client.post(
            f"{CAMPAIGNS_BASE}{campaign.id}/media/",
            {"video": mp4_upload(seconds=5), "video_poster": image_upload()},
            format="multipart",
        )
        self.assertEqual(uploaded.status_code, status.HTTP_200_OK)
        self.assertTrue(uploaded.data["video"].endswith(".mp4"))
        self.assertTrue(uploaded.data["video_poster"].endswith(".webp"))

        activated = self.client.patch(
            f"{CAMPAIGNS_BASE}{campaign.id}/",
            {"is_active": True},
            format="json",
        )
        self.assertEqual(activated.status_code, status.HTTP_200_OK)
        self.assertTrue(activated.data["is_active"])
        campaign.refresh_from_db()
        video_name = campaign.video.name
        video_storage = campaign.video.storage
        with self.captureOnCommitCallbacks(execute=True):
            campaign.delete()
        self.assertFalse(video_storage.exists(video_name))

    def test_switching_media_type_removes_replaced_file(self):
        campaign = self.create_campaign(
            is_active=False,
            media_type=HomeCampaign.MediaType.IMAGE,
            sheet_image=image_upload("old-campaign.png"),
        )
        old_name = campaign.sheet_image.name
        storage = campaign.sheet_image.storage
        self.assertTrue(storage.exists(old_name))
        self.authenticate(self.admin)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(
                f"{CAMPAIGNS_BASE}{campaign.id}/",
                {"media_type": HomeCampaign.MediaType.NONE},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(storage.exists(old_name))
