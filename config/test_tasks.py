from io import BytesIO

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase
from PIL import Image

from config.tasks import delete_storage_file_task
from markets.models import Market, MarketClassification


class ConfigCeleryTasksTests(TestCase):
    def test_delete_storage_file_task_deletes_unreferenced_file(self):
        buf = BytesIO()
        Image.new("RGB", (10, 10), color="green").save(buf, format="PNG")
        saved_name = default_storage.save(
            "test_cleanup_file.png", ContentFile(buf.getvalue())
        )
        self.assertTrue(default_storage.exists(saved_name))

        result = delete_storage_file_task.apply(args=["default", saved_name]).get()
        self.assertEqual(result["status"], "success")
        self.assertFalse(default_storage.exists(saved_name))

    def test_delete_storage_file_task_preserves_referenced_file(self):
        classification = MarketClassification.objects.create(name="Class 1")
        file_name = "referenced_market_logo.png"
        content = BytesIO()
        Image.new("RGB", (10, 10), color="red").save(content, format="PNG")
        saved_name = default_storage.save(file_name, ContentFile(content.getvalue()))

        market = Market.objects.create(
            name="Market With Logo",
            classification=classification,
            image=saved_name,
        )

        result = delete_storage_file_task.apply(args=["default", saved_name]).get()
        self.assertEqual(result["status"], "success")
        self.assertTrue(default_storage.exists(saved_name))

        # Cleanup
        default_storage.delete(saved_name)
