import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase
from PIL import Image

from .models import AppLaunchMedia


URL = "/api/v1/dashboard/app-media/"
User = get_user_model()


def small_png(name):
    content = BytesIO()
    Image.new("RGB", (2, 2), "blue").save(content, format="PNG")
    return SimpleUploadedFile(name, content.getvalue(), content_type="image/png")


class AppLaunchMediaTests(APITestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.admin = User.objects.create_user(
            username="app_media_admin", email="media-admin@example.com",
            phone="+213555810091", password="Password1!", role=User.Role.ADMIN,
        )
        self.client_user = User.objects.create_user(
            username="app_media_client", email="media-client@example.com",
            phone="+213555810092", password="Password1!", role=User.Role.CLIENT,
        )

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_public_read_and_admin_only_write(self):
        self.assertEqual(self.client.get(URL).status_code, 200)
        self.assertEqual(self.client.patch(URL, {"delivery_login": None}, format="json").status_code, 401)
        self.client.force_authenticate(self.client_user)
        self.assertEqual(self.client.patch(URL, {"delivery_login": None}, format="json").status_code, 403)

    def test_admin_can_upload_and_reset_market_video(self):
        self.client.force_authenticate(self.admin)
        video = SimpleUploadedFile("intro.mp4", b"\x00\x00\x00\x18ftypisom" + b"\x00" * 16, content_type="video/mp4")
        response = self.client.patch(URL, {"market_login_video": video}, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("/media/app-launch/login/", response.data["market_login_url"])
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(URL).data["market_login_url"], response.data["market_login_url"])
        self.client.force_authenticate(self.admin)
        reset = self.client.patch(URL, {"market_login": None}, format="json")
        self.assertEqual(reset.status_code, 200, reset.data)
        self.assertIsNone(reset.data["market_login_url"])
        self.assertFalse(AppLaunchMedia.objects.get(pk=1).market_login_video)

    def test_rejects_fake_video(self):
        self.client.force_authenticate(self.admin)
        fake = SimpleUploadedFile("fake.mp4", b"not a video", content_type="video/mp4")
        response = self.client.patch(URL, {"market_login_video": fake}, format="multipart")
        self.assertEqual(response.status_code, 400)
        wrong_type = SimpleUploadedFile(
            "fake.mp4", b"\x00\x00\x00\x18ftypisom" + b"\x00" * 16,
            content_type="application/octet-stream",
        )
        response = self.client.patch(URL, {"market_login_video": wrong_type}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_image_upload_replaces_video_and_onboarding_images_are_public(self):
        self.client.force_authenticate(self.admin)
        video = SimpleUploadedFile("intro.mp4", b"\x00\x00\x00\x18ftypisom" + b"\x00" * 16, content_type="video/mp4")
        self.assertEqual(self.client.patch(URL, {"market_login_video": video}, format="multipart").status_code, 200)
        response = self.client.patch(URL, {
            "market_login": small_png("login.png"),
            "onboarding_one": small_png("first.png"),
        }, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["market_login_url"].endswith(".webp"))
        self.assertIsNotNone(response.data["onboarding_one_url"])
        self.assertFalse(AppLaunchMedia.objects.get(pk=1).market_login_video)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(URL).data["onboarding_one_url"], response.data["onboarding_one_url"])
