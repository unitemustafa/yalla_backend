from io import BytesIO, StringIO
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from PIL import Image

from catalog.models import CategoryClassification, ProductCategory


def png_upload(name):
    output = BytesIO()
    Image.new("RGB", (2, 2), "orange").save(output, format="PNG")
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/png")


class MediaAuditCommandTests(TestCase):
    def test_generic_cleanup_removes_replaced_model_images(self):
        with TemporaryDirectory() as media_root, override_settings(
            MEDIA_ROOT=media_root
        ):
            classification = CategoryClassification.objects.create(name="Cleanup")
            category = ProductCategory.objects.create(
                classification=classification,
                name="Cleanup category",
                image=png_upload("first.png"),
            )
            storage = category.image.storage
            old_name = category.image.name

            category.image = png_upload("second.png")
            with self.captureOnCommitCallbacks(execute=True):
                category.save(update_fields=["image"])

            self.assertFalse(storage.exists(old_name))
            self.assertTrue(storage.exists(category.image.name))

    def test_reports_and_optionally_repairs_missing_and_orphan_files(self):
        with TemporaryDirectory() as media_root, override_settings(
            MEDIA_ROOT=media_root
        ):
            classification = CategoryClassification.objects.create(name="Audit")
            category = ProductCategory.objects.create(
                classification=classification,
                name="Audit category",
                image=png_upload("referenced.png"),
            )
            storage = category.image.storage
            missing_name = category.image.name
            storage.delete(missing_name)
            orphan_name = storage.save(
                "categories/orphan.png",
                png_upload("orphan.png"),
            )

            dry_run = StringIO()
            call_command("audit_media", stdout=dry_run)

            self.assertIn(f"MISSING catalog.ProductCategory.image", dry_run.getvalue())
            self.assertIn(f"ORPHAN {orphan_name}", dry_run.getvalue())
            category.refresh_from_db()
            self.assertEqual(category.image.name, missing_name)
            self.assertTrue(storage.exists(orphan_name))

            call_command(
                "audit_media",
                clear_missing=True,
                delete_orphans=True,
                stdout=StringIO(),
            )

            category.refresh_from_db()
            self.assertFalse(category.image)
            self.assertFalse(storage.exists(orphan_name))
