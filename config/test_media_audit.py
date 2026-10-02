from io import BytesIO, StringIO
from datetime import timedelta
from tempfile import TemporaryDirectory
import json
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from catalog.models import CategoryClassification, ProductCategory
from offers.models import Offer
from dashboard.models import MediaCleanup
from dashboard.tasks import cleanup_due_media


def png_upload(name, size=(2, 2)):
    output = BytesIO()
    Image.new("RGB", size, "orange").save(output, format="PNG")
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/png")


class MediaAuditCommandTests(TestCase):
    def test_verify_content_reports_corruption_and_accepts_other_ratios_without_mutating_media(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            classification = CategoryClassification.objects.create(name="Verified")
            corrupt_category = ProductCategory.objects.create(
                classification=classification,
                name="Corrupt stored image",
                image=png_upload("corrupt.png", size=(600, 600)),
            )
            corrupt_name = corrupt_category.image.name
            with corrupt_category.image.storage.open(corrupt_name, "wb") as content:
                content.write(b"stored file is corrupt")
            offer = Offer.objects.create(
                title="Alternative ratio", description="", discount=0,
                start_time=timezone.now() - timedelta(minutes=1),
                end_time=timezone.now() + timedelta(days=1),
                image=png_upload("banner.png", size=(1200, 1200)),
            )
            report_path = f"{media_root}/audit.json"
            output = StringIO()

            with self.assertRaises(CommandError):
                call_command(
                    "audit_media", verify_content=True, fail_on_invalid=True,
                    report_json=report_path, stdout=output,
                )

            report = json.loads(Path(report_path).read_text(encoding="utf-8"))
            invalid_names = {entry["name"] for entry in report["invalid"]}
            self.assertIn(corrupt_name, invalid_names)
            self.assertNotIn(offer.image.name, invalid_names)
            corrupt_category.refresh_from_db()
            offer.refresh_from_db()
            self.assertEqual(corrupt_category.image.name, corrupt_name)
            self.assertTrue(offer.image)

    def test_generic_cleanup_defers_replaced_files_and_removes_them_when_due(self):
        with (
            TemporaryDirectory() as media_root,
            override_settings(MEDIA_ROOT=media_root),
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

            self.assertTrue(storage.exists(old_name))
            cleanup = MediaCleanup.objects.get(name=old_name)
            self.assertGreater(cleanup.delete_after, timezone.now())
            cleanup_due_media.apply().get()
            self.assertTrue(storage.exists(old_name))
            cleanup.delete_after = timezone.now() - timedelta(seconds=1)
            cleanup.save(update_fields=["delete_after"])
            cleanup_due_media.apply().get()
            self.assertFalse(storage.exists(old_name))
            self.assertTrue(storage.exists(category.image.name))

    def test_due_cleanup_keeps_a_file_that_is_still_referenced(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            classification = CategoryClassification.objects.create(name="Referenced")
            category = ProductCategory.objects.create(
                classification=classification, name="Referenced category", image=png_upload("kept.png"),
            )
            storage = category.image.storage
            MediaCleanup.objects.create(
                storage_id="default", name=category.image.name,
                delete_after=timezone.now() - timedelta(seconds=1),
            )

            cleanup_due_media.apply().get()

            self.assertTrue(storage.exists(category.image.name))

    def test_reports_and_optionally_repairs_missing_and_orphan_files(self):
        with (
            TemporaryDirectory() as media_root,
            override_settings(MEDIA_ROOT=media_root),
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
