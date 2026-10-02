from config.media_test_tools import FFMPEG, FFPROBE
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
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
from dashboard.models import MediaCleanup, MediaJob
from dashboard.tasks import cleanup_due_media
from PIL import Image
from .models import HomeCampaign, HomeCampaignImage


User = get_user_model()
CAMPAIGNS_BASE = "/api/v1/offers/home-campaigns/"


def mp4_upload(seconds=5):
    ffmpeg = FFMPEG
    if not ffmpeg.is_file():
        raise RuntimeError("Portable FFmpeg is required for media integration tests.")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "campaign.mp4"
        subprocess.run([
            str(ffmpeg), "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
            f"color=c=blue:s=320x180:r=24:d={seconds}", "-c:v", "mpeg4", str(path),
        ], check=True, stdin=subprocess.DEVNULL)
        return SimpleUploadedFile("campaign.mp4", path.read_bytes(), content_type="video/mp4")


def image_upload(name="campaign.png"):
    content = BytesIO()
    Image.new("RGB", (1200, 675), "blue").save(content, format="PNG")
    return SimpleUploadedFile(name, content.getvalue(), content_type="image/png")


@override_settings(
    FFMPEG_BINARY=str(FFMPEG),
    FFPROBE_BINARY=str(FFPROBE),
)
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
        market_classification = MarketClassification.objects.create(
            name="Campaign Shops"
        )
        self.market = Market.objects.create(
            classification=market_classification,
            name="Campaign Market",
        )
        self.market.service_cities.add(self.city)
        category_classification = CategoryClassification.objects.create(
            name="Campaign Food"
        )
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
        results = (
            listed.data.get("results", [])
            if isinstance(listed.data, dict)
            else listed.data
        )
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

    def test_raw_video_upload_stays_pending_before_activation(self):
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
        campaign.refresh_from_db()
        self.assertIsNotNone(campaign.pending_video_job)
        self.assertFalse(campaign.video)

        activated = self.client.patch(
            f"{CAMPAIGNS_BASE}{campaign.id}/",
            {"is_active": True},
            format="json",
        )
        self.assertEqual(activated.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("media_type", activated.data)

    def test_raw_video_replacement_keeps_old_campaign_poster_until_job_is_ready(self):
        campaign = self.create_campaign(
            is_active=False,
            media_type=HomeCampaign.MediaType.VIDEO,
        )
        campaign.video.save("published.mp4", ContentFile(b"published"), save=False)
        campaign.video_poster.save("published.png", image_upload("published.png"), save=True)
        old_video, old_poster = campaign.video.name, campaign.video_poster.name
        self.authenticate(self.admin)

        response = self.client.post(
            f"{CAMPAIGNS_BASE}{campaign.id}/media/",
            {"video": mp4_upload(), "video_poster": image_upload("replacement.png")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        campaign.refresh_from_db()
        self.assertEqual(campaign.video.name, old_video)
        self.assertEqual(campaign.video_poster.name, old_poster)
        self.assertIsNotNone(campaign.pending_video_job)
        self.assertTrue(campaign.pending_video_job.custom_poster)

    def test_campaign_media_endpoint_rejects_pending_or_wrong_slot_job(self):
        campaign = self.create_campaign(is_active=False)
        pending = MediaJob.objects.create(owner=self.admin, slot="campaign")
        wrong_slot = MediaJob.objects.create(
            owner=self.admin, slot="market_login", state=MediaJob.State.READY,
        )
        wrong_slot.video.save("prepared.mp4", ContentFile(b"video"), save=False)
        wrong_slot.poster.save("prepared.png", image_upload("prepared.png"), save=False)
        wrong_slot.save(update_fields=["video", "poster"])
        self.authenticate(self.admin)

        pending_response = self.client.post(
            f"{CAMPAIGNS_BASE}{campaign.id}/media/", {"video_job_id": str(pending.pk)}, format="json",
        )
        wrong_slot_response = self.client.post(
            f"{CAMPAIGNS_BASE}{campaign.id}/media/", {"video_job_id": str(wrong_slot.pk)}, format="json",
        )

        self.assertEqual(pending_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("video_job_id", pending_response.data)
        self.assertEqual(wrong_slot_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("video_job_id", wrong_slot_response.data)

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

        response = self.client.patch(
            f"{CAMPAIGNS_BASE}{campaign.id}/",
            {"media_type": HomeCampaign.MediaType.NONE},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(storage.exists(old_name))
        self.assertTrue(MediaCleanup.objects.filter(name=old_name).exists())

    def test_multiple_images_upload_display_and_delete(self):
        campaign = self.create_campaign(
            is_active=False,
            media_type=HomeCampaign.MediaType.IMAGE,
        )
        self.authenticate(self.admin)
        upload = self.client.post(
            f"{CAMPAIGNS_BASE}{campaign.id}/media/",
            {"images": [image_upload("first.png"), image_upload("second.png")]},
            format="multipart",
        )
        self.assertEqual(upload.status_code, status.HTTP_200_OK)
        self.assertEqual(len(upload.data["additional_images"]), 2)
        self.assertEqual(HomeCampaignImage.objects.filter(campaign=campaign).count(), 2)

        activated = self.client.patch(
            f"{CAMPAIGNS_BASE}{campaign.id}/",
            {"is_active": True},
            format="json",
        )
        self.assertEqual(activated.status_code, status.HTTP_200_OK)
        self.authenticate(self.user)
        home = self.client.get("/api/v1/home/")
        self.assertEqual(home.status_code, status.HTTP_200_OK)
        self.assertEqual(len(home.data["home_campaign"]["media"]["image_urls"]), 2)

        self.authenticate(self.admin)
        image_id = upload.data["additional_images"][0]["id"]
        deleted = self.client.delete(
            f"{CAMPAIGNS_BASE}{campaign.id}/images/{image_id}/"
        )
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(HomeCampaignImage.objects.filter(campaign=campaign).count(), 1)

        last_image_id = upload.data["additional_images"][1]["id"]
        rejected = self.client.delete(
            f"{CAMPAIGNS_BASE}{campaign.id}/images/{last_image_id}/"
        )
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_invalid_additional_image_without_partial_upload(self):
        campaign = self.create_campaign(
            is_active=False,
            media_type=HomeCampaign.MediaType.IMAGE,
        )
        self.authenticate(self.admin)
        response = self.client.post(
            f"{CAMPAIGNS_BASE}{campaign.id}/media/",
            {
                "images": [
                    image_upload("valid.png"),
                    SimpleUploadedFile("bad.txt", b"bad", content_type="text/plain"),
                ]
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(HomeCampaignImage.objects.filter(campaign=campaign).exists())

    @patch("offers.views.HomeCampaignImage.objects.create", side_effect=OSError("storage unavailable"))
    def test_storage_failure_rolls_back_publication_and_keeps_previous_file(self, create_image):
        campaign = self.create_campaign(is_active=False, media_type=HomeCampaign.MediaType.IMAGE)
        campaign.sheet_image.save("published.png", image_upload(), save=True)
        published = campaign.sheet_image.name
        self.authenticate(self.admin)
        response = self.client.post(f"{CAMPAIGNS_BASE}{campaign.id}/media/", {
            "sheet_image": image_upload("replacement.png"),
            "images": [image_upload("extra.png")],
        }, format="multipart")
        campaign.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(campaign.sheet_image.name, published)
        self.assertTrue(campaign.sheet_image.storage.exists(published))
        self.assertFalse(campaign.additional_images.exists())
        self.assertFalse(MediaCleanup.objects.filter(name=published).exists())
        self.assertTrue(MediaCleanup.objects.exists())
        create_image.assert_called_once()
