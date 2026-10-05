from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from markets.serializers import HomeOfferSerializer
from .models import Offer
from .tests import offer_image_upload


class OfferImageFocusTests(APITestCase):
    def setUp(self):
        admin = get_user_model().objects.create_user(
            username="focus_admin", role="admin", password="Password1!"
        )
        self.client.force_authenticate(admin)
        self.offer = Offer.objects.create(
            title="Banner", type="announcement", show_in_general=True,
            discount=0, start_time=timezone.now() - timedelta(hours=1),
            end_time=timezone.now() + timedelta(days=1),
            announcement_url="https://example.com/offer",
        )
        self.path = f"/api/v1/offers/{self.offer.pk}/"

    def test_legacy_default_and_focus_round_trip_to_client(self):
        self.assertEqual(HomeOfferSerializer(self.offer).data["image_focus"], {"x": 0.5, "y": 0.5})
        focus = {"x": 0.2, "y": 0.8}
        response = self.client.patch(self.path, {"image_focus": focus}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["image_focus"], focus)
        self.offer.refresh_from_db()
        self.assertEqual(HomeOfferSerializer(self.offer).data["image_focus"], focus)

    def test_rejects_invalid_focus_without_changing_saved_value(self):
        for value in [None, {}, {"x": True, "y": 0.5}, {"x": -1, "y": 0.5},
                      {"x": 0.5, "y": 2}, {"x": "0.2", "y": 0.5}, {"x": 0.2, "y": 0.5, "extra": 1}]:
            with self.subTest(value=value):
                response = self.client.patch(self.path, {"image_focus": value}, format="json")
                self.assertEqual(response.status_code, 400, response.data)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.image_focus, {"x": 0.5, "y": 0.5})

    def test_multipart_image_and_focus_are_saved_together(self):
        response = self.client.post(self.path + "image/", {
            "image": offer_image_upload(), "image_focus": '{"x":0.3,"y":0.9}',
        }, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.offer.refresh_from_db()
        self.assertTrue(self.offer.image)
        self.assertEqual(self.offer.image_focus, {"x": 0.3, "y": 0.9})

    def test_failed_image_write_rolls_back_focus(self):
        with patch("offers.images.Offer.save", side_effect=RuntimeError("write failed")):
            response = self.client.post(self.path + "image/", {
                "image": offer_image_upload(), "image_focus": '{"x":0.3,"y":0.9}',
            }, format="multipart")
        self.assertEqual(response.status_code, 503)
        self.offer.refresh_from_db()
        self.assertFalse(self.offer.image)
        self.assertEqual(self.offer.image_focus, {"x": 0.5, "y": 0.5})
