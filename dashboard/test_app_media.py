from config.media_test_tools import FFMPEG, FFPROBE
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
import subprocess

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase
from PIL import Image

from .models import AppLaunchMedia


URL = "/api/v1/dashboard/app-media/"
User = get_user_model()




def small_png(name, size=(800, 450)):
    content = BytesIO()
    Image.new("RGB", size, "blue").save(content, format="PNG")
    return SimpleUploadedFile(name, content.getvalue(), content_type="image/png")


class AppLaunchMediaTests(APITestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(
            MEDIA_ROOT=self.media_root,
            PRIVATE_MEDIA_ROOT=str(Path(self.media_root) / "private"),
            FFMPEG_BINARY=str(FFMPEG),
            FFPROBE_BINARY=str(FFPROBE),
        )
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

    def real_video(self):
        if not FFMPEG.is_file() or not FFPROBE.is_file():
            self.skipTest("Portable FFmpeg is required for media integration tests.")
        target = Path(self.media_root) / "intro.mp4"
        subprocess.run([
            str(FFMPEG), "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
            "color=c=blue:s=320x180:r=24:d=1", "-c:v", "mpeg4", str(target),
        ], check=True, stdin=subprocess.DEVNULL)
        return SimpleUploadedFile("intro.mp4", target.read_bytes(), content_type="video/mp4")

    def test_public_read_and_admin_only_write(self):
        self.assertEqual(self.client.get(URL).status_code, 200)
        self.assertEqual(self.client.patch(URL, {"delivery_login": None}, format="json").status_code, 401)
        self.client.force_authenticate(self.client_user)
        self.assertEqual(self.client.patch(URL, {"delivery_login": None}, format="json").status_code, 403)

    def test_admin_uploads_market_video_to_a_private_pending_job_then_can_cancel_it(self):
        self.client.force_authenticate(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(URL, {"market_login_video": self.real_video()}, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["market_login_url"])
        self.assertEqual(response.data["market_login_processing"]["state"], "pending")
        job_id = response.data["market_login_processing"]["id"]
        self.client.force_authenticate(user=None)
        self.assertIsNone(self.client.get(URL).data["market_login_url"])
        self.client.force_authenticate(self.admin)
        cancelled = self.client.delete(f"/api/v1/dashboard/media-jobs/{job_id}/")
        self.assertEqual(cancelled.status_code, 204)
        media = AppLaunchMedia.objects.get(pk=1)
        self.assertIsNone(media.market_login_pending_job)
        self.assertFalse(media.market_login_video)

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

    def test_rejects_oversized_image_with_its_field_name(self):
        self.client.force_authenticate(self.admin)
        upload = small_png("large.png")
        upload.seek(0, 2)
        upload.write(b"\x00" * (5 * 1024 * 1024))
        upload.seek(0)
        response = self.client.patch(URL, {"market_login": upload}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("market_login", response.data)
        self.assertIn("5 MB", str(response.data["market_login"]))

    def test_small_images_of_any_ratio_can_be_uploaded_to_every_slot(self):
        self.client.force_authenticate(self.admin)
        for field in ("market_login", "delivery_login"):
            for size in ((1, 1), (32, 96), (96, 32)):
                with self.subTest(field=field, size=size):
                    response = self.client.patch(URL, {
                        field: small_png(f"{field}.png", size=size),
                    }, format="multipart")
                    self.assertEqual(response.status_code, 200, response.data)
                    self.assertTrue(response.data[f"{field}_url"].endswith(".webp"))
                    stored = getattr(AppLaunchMedia.objects.get(pk=1), field)
                    with stored.open("rb") as content, Image.open(content) as image:
                        self.assertEqual(image.size, size)

    def test_image_upload_replaces_video_and_is_public(self):
        self.client.force_authenticate(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.patch(URL, {"market_login_video": self.real_video()}, format="multipart").status_code, 200)
        response = self.client.patch(URL, {
            "market_login": small_png("login.png"),
            "market_login_focus": '{"x":0.25,"y":0.75}',
        }, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["market_login_url"].endswith(".webp"))
        self.assertIsNone(response.data["onboarding_one_url"])
        self.assertEqual(response.data["market_login_focus"], {"x": 0.25, "y": 0.75})
        self.assertFalse(AppLaunchMedia.objects.get(pk=1).market_login_video)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(URL).data["onboarding_one_url"], response.data["onboarding_one_url"])

    def test_admin_cannot_change_or_remove_bundled_onboarding_images(self):
        self.client.force_authenticate(self.admin)
        for field in ("onboarding_one", "onboarding_two", "onboarding_three"):
            with self.subTest(field=field):
                response = self.client.patch(URL, {
                    field: small_png("onboarding.png"),
                    "delivery_login": small_png("delivery.png"),
                }, format="multipart")
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn(field, response.data)
                self.assertFalse(getattr(AppLaunchMedia.objects.get(pk=1), field))
                self.assertFalse(AppLaunchMedia.objects.get(pk=1).delivery_login)
                response = self.client.patch(URL, {field: None}, format="json")
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn(field, response.data)

    def test_legacy_onboarding_uploads_are_not_served_to_apps(self):
        media = AppLaunchMedia.objects.create(pk=1)
        for field in ("onboarding_one", "onboarding_two", "onboarding_three"):
            setattr(media, field, small_png(f"{field}.png"))
        media.save()
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        for field in ("onboarding_one", "onboarding_two", "onboarding_three"):
            self.assertIsNone(response.data[f"{field}_url"])
