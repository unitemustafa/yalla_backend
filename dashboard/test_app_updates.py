import hashlib
import shutil
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import resolve
from rest_framework.test import APITestCase

from .models import DeliveryAppRelease


RELEASES_URL = "/api/v1/dashboard/app-updates/"
LATEST_URL = "/api/v1/dashboard/app-updates/latest/"
User = get_user_model()


def apk_upload(name="yalla-delivery.apk"):
    content = BytesIO()
    with zipfile.ZipFile(content, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("AndroidManifest.xml", b"manifest")
        archive.writestr("classes.dex", b"dex")
    return SimpleUploadedFile(
        name, content.getvalue(), content_type="application/vnd.android.package-archive"
    )


class DeliveryAppUpdateTests(APITestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.admin = User.objects.create_user(
            username="updates_admin", email="updates-admin@example.com",
            phone="+213555810101", password="Password1!", role=User.Role.ADMIN,
        )
        self.courier = User.objects.create_user(
            username="updates_courier", email="updates-courier@example.com",
            phone="+213555810102", password="Password1!", role=User.Role.REPRESENTATIVE,
        )

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def publish(self, version_code=4016, **extra):
        payload = {
            "version_code": version_code,
            "version_name": "1.0.12",
            "release_notes": "إصلاحات مهمة",
            "apk": apk_upload(),
            **extra,
        }
        return self.client.post(RELEASES_URL, payload, format="multipart")

    def test_given_admin_and_valid_apk_when_publishing_then_raw_apk_and_metadata_are_preserved(self):
        raw_apk = apk_upload()
        raw_bytes = raw_apk.read()
        raw_apk.seek(0)
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            RELEASES_URL,
            {
                "version_code": 4016,
                "version_name": "1.0.12",
                "release_notes": "إصلاحات مهمة",
                "apk": raw_apk,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201, response.data)
        release = DeliveryAppRelease.objects.get(version_code=4016)
        self.assertTrue(release.is_active)
        self.assertEqual(release.sha256, hashlib.sha256(raw_bytes).hexdigest())
        self.assertEqual(release.file_size, len(raw_bytes))
        self.assertEqual(release.apk.read(), raw_bytes)
        self.assertTrue(response.data["download_url"].endswith(release.apk.name))

    def test_given_newer_active_release_when_public_client_checks_then_highest_newer_integer_is_returned(self):
        self.client.force_authenticate(self.admin)
        first = self.publish(9, version_name="0.0.9")
        second = self.publish(10, version_name="0.0.10")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(
            list(DeliveryAppRelease.objects.values_list("version_code", flat=True)),
            [10, 9],
        )
        self.assertTrue(
            DeliveryAppRelease.objects.filter(is_active=True, version_code__gt=8).exists()
        )
        self.client.force_authenticate(user=None)

        response = self.client.get(f"{LATEST_URL}?version_code=8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(resolve("/api/v1/dashboard/app-updates/latest/").url_name, "latest-delivery-app-release")
        self.assertIsNotNone(response.data["update"], response.data)
        self.assertEqual(response.data["update"]["version_code"], 10)
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_given_no_newer_active_release_when_public_client_checks_then_update_is_null(self):
        self.client.force_authenticate(self.admin)
        created = self.publish(4016)
        self.assertEqual(created.status_code, 201, created.data)
        release_id = created.data["id"]
        self.assertEqual(
            self.client.patch(
                f"{RELEASES_URL}{release_id}/", {"is_active": False}, format="json"
            ).status_code,
            200,
        )
        self.client.force_authenticate(user=None)

        response = self.client.get(f"{LATEST_URL}?version_code=1")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["update"])

    def test_given_invalid_latest_version_query_when_public_client_checks_then_400(self):
        for query in ("", "0", "not-a-number", "2100000001"):
            with self.subTest(query=query):
                response = self.client.get(f"{LATEST_URL}?version_code={query}")
                self.assertEqual(response.status_code, 400)

    def test_given_invalid_release_status_payload_when_admin_patches_then_400(self):
        release = DeliveryAppRelease.objects.create(
            version_code=4016,
            version_name="1.0.12",
            apk=apk_upload(),
            sha256="a" * 64,
            file_size=1,
            created_by=self.admin,
        )
        self.client.force_authenticate(self.admin)
        for payload in ([], {}, {"is_active": True, "extra": True}):
            with self.subTest(payload=payload):
                response = self.client.patch(
                    f"{RELEASES_URL}{release.id}/", payload, format="json"
                )
                self.assertEqual(response.status_code, 400)

    def test_given_anonymous_or_courier_when_managing_releases_then_access_is_denied(self):
        self.assertEqual(self.client.get(RELEASES_URL).status_code, 401)
        self.assertEqual(self.publish().status_code, 401)
        self.client.force_authenticate(self.courier)
        self.assertEqual(self.client.get(RELEASES_URL).status_code, 403)
        self.assertEqual(self.publish().status_code, 403)
        release = DeliveryAppRelease.objects.create(
            version_code=4016,
            version_name="1.0.12",
            apk=apk_upload(),
            sha256="a" * 64,
            file_size=1,
            created_by=self.admin,
        )
        self.assertEqual(
            self.client.patch(
                f"{RELEASES_URL}{release.id}/", {"is_active": False}, format="json"
            ).status_code,
            403,
        )

    def test_given_invalid_package_or_metadata_when_publishing_then_release_is_rejected(self):
        self.client.force_authenticate(self.admin)

        invalid_extension = self.publish(apk=apk_upload("yalla.zip"))
        fake_apk = self.publish(apk=SimpleUploadedFile("yalla.apk", b"not an apk"))
        missing_manifest = BytesIO()
        with zipfile.ZipFile(missing_manifest, "w") as archive:
            archive.writestr("classes.dex", b"dex")
        missing_manifest_response = self.publish(
            apk=SimpleUploadedFile("yalla.apk", missing_manifest.getvalue())
        )
        invalid_version = self.publish(version_code=0)

        for response in (
            invalid_extension,
            fake_apk,
            missing_manifest_response,
            invalid_version,
        ):
            with self.subTest(status=response.status_code, data=response.data):
                self.assertEqual(response.status_code, 400)
        self.assertEqual(DeliveryAppRelease.objects.count(), 0)

    def test_given_file_larger_than_limit_when_publishing_then_release_is_rejected(self):
        self.client.force_authenticate(self.admin)
        with patch("dashboard.app_updates.MAX_APK_BYTES", 1):
            response = self.publish(apk=apk_upload())

        self.assertEqual(response.status_code, 400)
        self.assertIn("apk", response.data)

    def test_given_existing_version_when_publishing_then_duplicate_is_rejected(self):
        self.client.force_authenticate(self.admin)
        first = self.publish(4016)
        second = self.publish(4016)

        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 400)
        self.assertIn("version_code", second.data)
        self.assertEqual(DeliveryAppRelease.objects.count(), 1)
