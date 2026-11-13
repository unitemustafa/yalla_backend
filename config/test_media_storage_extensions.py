import tempfile

from django.core.files.base import ContentFile
from django.test import SimpleTestCase, override_settings

from .media import RawPublicMediaStorage


class RawPublicMediaExtensionTests(SimpleTestCase):
    def test_default_video_and_explicit_apk_keep_their_extension_and_bytes(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            for extension in ("mp4", "apk"):
                storage = (
                    RawPublicMediaStorage()
                    if extension == "mp4"
                    else RawPublicMediaStorage(extension="apk")
                )
                with self.subTest(extension=extension):
                    name = storage.save(f"test/file.{extension}", ContentFile(b"raw data"))
                    self.assertTrue(name.endswith(f".{extension}"), name)
                    with storage.open(name) as stored:
                        self.assertEqual(stored.read(), b"raw data")

    def test_apk_extension_is_preserved_in_migration_serialization(self):
        storage = RawPublicMediaStorage(extension="apk")
        path, args, kwargs = storage.deconstruct()
        self.assertEqual(path, "config.media.RawPublicMediaStorage")
        self.assertEqual(args, ())
        self.assertEqual(kwargs, {"extension": "apk"})
