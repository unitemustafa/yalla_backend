import io
from unittest.mock import patch
from PIL import Image

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient
from storages.backends.s3 import S3Storage

from catalog.models import CategoryClassification, ProductCategory
from config.media import (
    OptimizedPublicMediaStorage,
    RawPublicMediaStorage,
    OptimizedPrivateMediaStorage,
    is_s3_storage_active,
)
from config.tasks import delete_storage_file_task
from markets.models import MarketClassification, Market
from orders.models import Order

User = get_user_model()


def make_png_content(color="blue", size=(20, 20)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


class ObjectStorageUnitTests(TestCase):
    def test_storage_backend_toggle_resolves_correct_engine(self):
        with override_settings(STORAGE_BACKEND="local"):
            self.assertFalse(is_s3_storage_active())
            pub_storage = OptimizedPublicMediaStorage()
            backend = pub_storage.get_backend()
            self.assertIsInstance(backend, FileSystemStorage)

        with override_settings(
            STORAGE_BACKEND="s3",
            AWS_ACCESS_KEY_ID="dummy-access-key",
            AWS_SECRET_ACCESS_KEY="dummy-secret-key",
            AWS_STORAGE_BUCKET_NAME="test-public-bucket",
            AWS_STORAGE_PRIVATE_BUCKET_NAME="test-private-bucket",
            AWS_S3_ENDPOINT_URL="https://r2.example.com",
            AWS_S3_CUSTOM_DOMAIN="media.example.com",
        ):
            self.assertTrue(is_s3_storage_active())
            pub_storage = OptimizedPublicMediaStorage()
            backend = pub_storage.get_backend()
            self.assertIsInstance(backend, S3Storage)
            self.assertEqual(backend.bucket_name, "test-public-bucket")
            self.assertEqual(backend.custom_domain, "media.example.com")
            self.assertFalse(backend.querystring_auth)

            priv_storage = OptimizedPrivateMediaStorage()
            priv_backend = priv_storage.get_backend()
            self.assertIsInstance(priv_backend, S3Storage)
            self.assertEqual(priv_backend.bucket_name, "test-private-bucket")
            self.assertTrue(priv_backend.querystring_auth)
            self.assertIsNone(priv_backend.custom_domain)

    @override_settings(
        STORAGE_BACKEND="s3",
        AWS_ACCESS_KEY_ID="dummy-access-key",
        AWS_SECRET_ACCESS_KEY="dummy-secret-key",
        AWS_STORAGE_BUCKET_NAME="test-public-bucket",
        AWS_S3_CUSTOM_DOMAIN="media.example.com",
    )
    def test_public_media_storage_optimizes_to_webp_and_generates_cdn_url(self):
        pub_storage = OptimizedPublicMediaStorage()
        png_bytes = make_png_content("green", (40, 40))

        with patch.object(S3Storage, "save") as mock_save:
            mock_save.side_effect = lambda name, content, max_length=None: name

            saved_name = pub_storage.save("categories/icon.png", ContentFile(png_bytes))

            self.assertTrue(saved_name.startswith("categories/"))
            self.assertTrue(saved_name.endswith(".webp"))
            self.assertTrue(mock_save.called)

            saved_content = mock_save.call_args[0][1]
            saved_bytes = saved_content.read()
            with Image.open(io.BytesIO(saved_bytes)) as img:
                self.assertEqual(img.format, "WEBP")

            public_url = pub_storage.url(saved_name)
            self.assertEqual(public_url, f"https://media.example.com/{saved_name}")

    @override_settings(
        STORAGE_BACKEND="s3",
        AWS_ACCESS_KEY_ID="dummy-access-key",
        AWS_SECRET_ACCESS_KEY="dummy-secret-key",
        AWS_STORAGE_BUCKET_NAME="test-public-bucket",
        AWS_S3_CUSTOM_DOMAIN="media.example.com",
    )
    def test_raw_public_media_storage_preserves_mp4_bytes(self):
        raw_storage = RawPublicMediaStorage()
        fake_mp4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42"

        with patch.object(S3Storage, "save") as mock_save:
            mock_save.side_effect = lambda name, content, max_length=None: name

            saved_name = raw_storage.save("campaigns/clip.mp4", ContentFile(fake_mp4))

            self.assertTrue(saved_name.startswith("campaigns/"))
            self.assertTrue(saved_name.endswith(".mp4"))
            self.assertTrue(mock_save.called)
            saved_content = mock_save.call_args[0][1]
            self.assertEqual(saved_content.read(), fake_mp4)

    @override_settings(
        STORAGE_BACKEND="s3",
        AWS_ACCESS_KEY_ID="dummy-access-key",
        AWS_SECRET_ACCESS_KEY="dummy-secret-key",
        AWS_STORAGE_BUCKET_NAME="test-public-bucket",
        AWS_STORAGE_PRIVATE_BUCKET_NAME="test-private-bucket",
        AWS_PRESIGNED_EXPIRY=300,
    )
    def test_private_media_storage_generates_presigned_url(self):
        priv_storage = OptimizedPrivateMediaStorage()
        with patch.object(S3Storage, "url") as mock_url:
            mock_url.return_value = "https://r2.example.com/test-private-bucket/orders/order.webp?X-Amz-Signature=fake123&X-Amz-Expires=300"
            signed_url = priv_storage.url("orders/order.webp")
            self.assertIn("X-Amz-Signature=fake123", signed_url)
            self.assertIn("X-Amz-Expires=300", signed_url)


class OrderPrivateMediaS3RedirectTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="admin_storage_test",
            email="admin_storage@example.com",
            phone="+201000000001",
            role=User.Role.ADMIN,
        )
        self.customer = User.objects.create_user(
            username="customer_storage_test",
            email="customer_storage@example.com",
            phone="+201000000002",
            role=User.Role.CLIENT,
        )
        self.other_customer = User.objects.create_user(
            username="other_customer_storage_test",
            email="other_storage@example.com",
            phone="+201000000003",
            role=User.Role.CLIENT,
        )
        self.market_class = MarketClassification.objects.create(name="Supermarket")
        self.market = Market.objects.create(
            name="Cairo Store",
            classification=self.market_class,
        )
        self.order = Order.objects.create(
            user=self.customer,
            market=self.market,
            payment_method="cash",
            image="orders/receipt.webp",
            delivery_proof="delivery-proofs/proof.webp",
        )

    @override_settings(
        STORAGE_BACKEND="s3",
        AWS_ACCESS_KEY_ID="dummy-access-key",
        AWS_SECRET_ACCESS_KEY="dummy-secret-key",
        AWS_STORAGE_BUCKET_NAME="test-public-bucket",
        AWS_STORAGE_PRIVATE_BUCKET_NAME="test-private-bucket",
    )
    def test_authorized_user_receives_302_redirect_to_presigned_url(self):
        self.client.force_authenticate(self.customer)

        fake_signed_url = "https://r2.example.com/test-private-bucket/orders/signed.webp?X-Amz-Signature=abc"
        with patch.object(S3Storage, "url", return_value=fake_signed_url):
            response = self.client.get(f"/api/v1/orders/{self.order.id}/image/")
            self.assertEqual(response.status_code, status.HTTP_302_FOUND)
            self.assertEqual(response["Location"], fake_signed_url)
            self.assertEqual(response["Cache-Control"], "private, no-store")

            # Also check delivery proof endpoint
            proof_response = self.client.get(
                f"/api/v1/orders/{self.order.id}/delivery-proof/"
            )
            self.assertEqual(proof_response.status_code, status.HTTP_302_FOUND)
            self.assertEqual(proof_response["Location"], fake_signed_url)
            self.assertEqual(proof_response["Cache-Control"], "private, no-store")

    @override_settings(
        STORAGE_BACKEND="s3",
        AWS_ACCESS_KEY_ID="dummy-access-key",
        AWS_SECRET_ACCESS_KEY="dummy-secret-key",
        AWS_STORAGE_BUCKET_NAME="test-public-bucket",
        AWS_STORAGE_PRIVATE_BUCKET_NAME="test-private-bucket",
    )
    def test_unauthorized_user_is_forbidden_even_on_s3(self):
        self.client.force_authenticate(self.other_customer)
        response = self.client.get(f"/api/v1/orders/{self.order.id}/image/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CeleryAndCleanupS3Tests(TestCase):
    @override_settings(
        STORAGE_BACKEND="s3",
        AWS_ACCESS_KEY_ID="dummy-access-key",
        AWS_SECRET_ACCESS_KEY="dummy-secret-key",
        AWS_STORAGE_BUCKET_NAME="test-public-bucket",
    )
    def test_delete_storage_file_task_invokes_s3_delete(self):
        with (
            patch.object(S3Storage, "exists", return_value=True),
            patch.object(S3Storage, "delete") as mock_delete,
        ):
            result = delete_storage_file_task("default", "products/orphan.webp")
            self.assertEqual(result["status"], "success")
            mock_delete.assert_called_once_with("products/orphan.webp")

    @override_settings(
        STORAGE_BACKEND="s3",
        AWS_ACCESS_KEY_ID="dummy-access-key",
        AWS_SECRET_ACCESS_KEY="dummy-secret-key",
        AWS_STORAGE_BUCKET_NAME="test-public-bucket",
    )
    @override_settings(
        STORAGE_BACKEND="s3",
        AWS_ACCESS_KEY_ID="dummy-access-key",
        AWS_SECRET_ACCESS_KEY="dummy-secret-key",
        AWS_STORAGE_BUCKET_NAME="test-public-bucket",
    )
    def test_audit_media_command_with_s3(self):
        classification = CategoryClassification.objects.create(name="Audit S3")
        category = ProductCategory.objects.create(
            classification=classification,
            name="Audit Category",
            image="categories/referenced.webp",
        )

        out = io.StringIO()
        with (
            patch.object(S3Storage, "exists", return_value=True),
            patch.object(
                S3Storage, "listdir", return_value=([], ["categories/referenced.webp"])
            ),
        ):
            call_command("audit_media", stdout=out)
            output = out.getvalue()
            self.assertIn("Media audit complete", output)
            self.assertIn("missing=0", output)
            self.assertIn("orphans=0", output)
