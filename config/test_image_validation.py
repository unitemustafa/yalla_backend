from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image
from rest_framework import serializers

from .image_validation import validate_safe_image


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
