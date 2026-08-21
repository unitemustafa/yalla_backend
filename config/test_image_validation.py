from io import BytesIO
import re
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image
from rest_framework import serializers

from .image_validation import validate_safe_image
from .media import OptimizedPublicMediaStorage


def image_upload(*, name="image.png", content_type="image/png", size=(4, 4)):
    output = BytesIO()
    Image.new("RGB", size, "white").save(output, format="PNG")
    return SimpleUploadedFile(name, output.getvalue(), content_type=content_type)


class SafeImageValidationTests(SimpleTestCase):
    def test_accepts_matching_decoded_image(self):
        upload = image_upload()
        self.assertIs(validate_safe_image(upload), upload)

    def test_rejects_corrupt_image(self):
        upload = SimpleUploadedFile(
            "image.png",
            b"not really a png",
            content_type="image/png",
        )
        with self.assertRaises(serializers.ValidationError):
            validate_safe_image(upload)

    def test_rejects_spoofed_extension_and_content_type(self):
        upload = image_upload(name="image.jpg", content_type="image/jpeg")
        with self.assertRaises(serializers.ValidationError):
            validate_safe_image(upload)

    @patch("config.image_validation.MAX_IMAGE_PIXELS", 10)
    def test_rejects_excessive_pixel_count(self):
        with self.assertRaises(serializers.ValidationError):
            validate_safe_image(image_upload(size=(4, 4)))


class OptimizedImageStorageTests(SimpleTestCase):
    def test_generates_uuid_webp_resizes_and_removes_metadata(self):
        output = BytesIO()
        source = Image.new("RGB", (2000, 1000), "blue")
        source.save(output, format="JPEG", exif=Image.Exif())
        upload = SimpleUploadedFile(
            "original.jpg",
            output.getvalue(),
            content_type="image/jpeg",
        )

        with TemporaryDirectory() as root:
            storage = OptimizedPublicMediaStorage(
                location=root,
                base_url="/media/",
            )
            stored_name = storage.save("products/original.jpg", upload)

            self.assertRegex(
                stored_name,
                re.compile(r"^products/[0-9a-f]{32}\.webp$"),
            )
            with storage.open(stored_name, "rb") as stored:
                with Image.open(stored) as optimized:
                    self.assertEqual(optimized.format, "WEBP")
                    self.assertEqual(optimized.size, (1600, 800))
                    self.assertNotIn("exif", optimized.info)

    def test_applies_exif_orientation_and_preserves_transparency(self):
        jpeg = BytesIO()
        exif = Image.Exif()
        exif[274] = 6
        exif[315] = "metadata must be removed"
        Image.new("RGB", (4, 2), "red").save(
            jpeg,
            format="JPEG",
            exif=exif,
        )
        transparent_png = BytesIO()
        Image.new("RGBA", (3, 3), (0, 0, 255, 0)).save(
            transparent_png,
            format="PNG",
        )

        with TemporaryDirectory() as root:
            storage = OptimizedPublicMediaStorage(location=root)
            oriented_name = storage.save(
                "products/oriented.jpg",
                SimpleUploadedFile("oriented.jpg", jpeg.getvalue()),
            )
            transparent_name = storage.save(
                "products/transparent.png",
                SimpleUploadedFile(
                    "transparent.png",
                    transparent_png.getvalue(),
                ),
            )

            with storage.open(oriented_name, "rb") as stored:
                with Image.open(stored) as oriented:
                    self.assertEqual(oriented.size, (2, 4))
                    self.assertNotIn("exif", oriented.info)
            with storage.open(transparent_name, "rb") as stored:
                with Image.open(stored) as transparent:
                    self.assertEqual(transparent.convert("RGBA").getpixel((1, 1))[3], 0)
            self.assertNotEqual(oriented_name, transparent_name)
