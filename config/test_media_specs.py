from io import BytesIO
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image
from rest_framework import serializers

from .media import OptimizedPublicMediaStorage
from .media_specs import media_contract, validate_focal_point, validate_media_image


def image_upload(*, name="image.png", size=(1600, 800), mode="RGB", exif=None, image_format=None):
    content = BytesIO()
    image = Image.new(mode, size, (20, 90, 220, 0) if "A" in mode else "blue")
    actual_format = image_format or ("JPEG" if name.endswith(".jpg") else "PNG")
    options = {"format": actual_format}
    if exif is not None:
        options["exif"] = exif
    image.save(content, **options)
    return SimpleUploadedFile(
        name, content.getvalue(),
        content_type="image/jpeg" if actual_format == "JPEG" else "image/png",
    )


class MediaSpecsValidationTests(SimpleTestCase):
    def test_every_slot_accepts_small_images_and_arbitrary_ratios(self):
        for key in media_contract()["images"]:
            for size in [(1, 1), (32, 96), (96, 32), (799, 800)]:
                with self.subTest(slot=key, size=size):
                    upload = image_upload(size=size)
                    upload.seek(8)
                    self.assertIs(validate_media_image(upload, key), upload)
                    self.assertEqual(upload.tell(), 8)

    def test_contract_keeps_dimensions_advisory_for_every_slot(self):
        for key, spec in media_contract()["images"].items():
            with self.subTest(slot=key):
                self.assertEqual(spec["minimumWidth"], 1)
                self.assertEqual(spec["minimumHeight"], 1)
                self.assertFalse(spec["ratioRequired"])
                self.assertGreater(spec["width"], 1)
                self.assertGreater(spec["height"], 1)

    def test_empty_optional_image_is_accepted(self):
        self.assertIsNone(validate_media_image(None, "product"))

    def test_offer_banner_contract_matches_the_taller_app_viewport(self):
        spec = media_contract()["images"]["offerBanner"]
        self.assertEqual((spec["width"], spec["height"]), (1600, 700))
        self.assertEqual((spec["safeWidth"], spec["safeHeight"]), (1200, 525))
        self.assertEqual(spec["fit"], "cover")
        for size in [(1600, 700), (1600, 600)]:
            with self.subTest(size=size):
                upload = image_upload(size=size)
                self.assertIs(validate_media_image(upload, "offerBanner"), upload)

    def test_store_cover_contract_preserves_the_complete_image_and_other_ratios(self):
        spec = media_contract()["images"]["storeCover"]
        self.assertEqual(spec["fit"], "contain")
        self.assertFalse(spec["ratioRequired"])
        for size in [(1600, 900), (1600, 1000), (1200, 1200)]:
            with self.subTest(size=size):
                upload = image_upload(size=size)
                self.assertIs(validate_media_image(upload, "storeCover"), upload)

    def test_product_accepts_a_rectangular_image_without_imposing_a_crop_ratio(self):
        upload = image_upload(size=(1600, 800))

        self.assertIs(validate_media_image(upload, "product"), upload)

    def test_product_uses_exif_oriented_dimensions(self):
        exif = Image.Exif()
        exif[274] = 6
        upload = image_upload(name="oriented.jpg", size=(800, 1600), exif=exif)

        self.assertIs(validate_media_image(upload, "product"), upload)

    def test_rejects_misleading_or_corrupt_images(self):
        with self.assertRaisesMessage(serializers.ValidationError, "extension"):
            validate_media_image(image_upload(name="image.jpg", image_format="PNG"), "product")
        corrupt = SimpleUploadedFile("image.png", b"not an image", content_type="image/png")
        with self.assertRaisesMessage(serializers.ValidationError, "non-corrupted"):
            validate_media_image(corrupt, "product")

    def test_focal_point_requires_finite_normalized_coordinates(self):
        self.assertEqual(validate_focal_point({"x": 0.25, "y": 1}), {"x": 0.25, "y": 1})
        for value in ({"x": -0.1, "y": 0.5}, {"x": float("nan"), "y": 0.5}, {"x": True, "y": 0.5}, {"x": 0.5}):
            with self.subTest(value=value), self.assertRaises(serializers.ValidationError):
                validate_focal_point(value)


class MediaOptimizerContractTests(SimpleTestCase):
    def test_optimizer_preserves_aspect_transparency_and_strips_metadata(self):
        exif = Image.Exif()
        exif[274] = 6
        exif[315] = "remove this metadata"
        opaque = image_upload(name="oriented.jpg", size=(800, 1600), exif=exif)
        transparent = image_upload(name="transparent.png", size=(2000, 1000), mode="RGBA")

        with TemporaryDirectory() as directory:
            storage = OptimizedPublicMediaStorage(location=directory)
            opaque_name = storage.save("products/oriented.jpg", opaque)
            transparent_name = storage.save("products/transparent.png", transparent)
            with storage.open(opaque_name) as output:
                with Image.open(output) as result:
                    self.assertEqual(result.format, "WEBP")
                    self.assertEqual(result.size, (1600, 800))
                    self.assertNotIn("exif", result.info)
            with storage.open(transparent_name) as output:
                with Image.open(output) as result:
                    self.assertEqual(result.size, (1600, 800))
                    self.assertEqual(result.convert("RGBA").getpixel((1, 1))[3], 0)
