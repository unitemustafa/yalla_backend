from unittest import TestCase

from .cloudinary_settings import build_cloudinary_storage_settings


class CloudinaryStorageSettingsTests(TestCase):
    def test_cloudinary_url_is_not_overwritten_with_empty_explicit_values(self):
        settings = build_cloudinary_storage_settings(
            {"CLOUDINARY_URL": "cloudinary://key:secret@example-cloud"}
        )

        self.assertEqual(settings, {"SECURE": True})

    def test_complete_explicit_credentials_are_forwarded(self):
        settings = build_cloudinary_storage_settings(
            {
                "CLOUDINARY_CLOUD_NAME": "example-cloud",
                "CLOUDINARY_API_KEY": "key",
                "CLOUDINARY_API_SECRET": "secret",
            }
        )

        self.assertEqual(
            settings,
            {
                "SECURE": True,
                "CLOUD_NAME": "example-cloud",
                "API_KEY": "key",
                "API_SECRET": "secret",
            },
        )

