from django.apps import apps
from django.core.management import call_command
from django.test import TestCase

from accounts.models import CourierProfile
from locations.models import Address, DeliveryArea, ServiceCity


EPHEMERAL_MODEL_LABELS = {
    "accounts.OTPCooldown",
}


class SeedDataCommandTests(TestCase):
    def test_seed_data_matches_current_location_schema(self):
        call_command("seed_data", verbosity=0)
        call_command("seed_data", verbosity=0)

        representative_profile = CourierProfile.objects.select_related(
            "user",
            "delivery_area__service_city",
        ).get(user__email="seed.courier@yalla.test")

        self.assertEqual(ServiceCity.objects.count(), 4)
        self.assertEqual(DeliveryArea.objects.count(), 8)
        self.assertIsNotNone(representative_profile.delivery_area.service_city)
        self.assertTrue(
            Address.objects.filter(
                user=representative_profile.user,
                is_default=True,
            ).exists()
        )

    def test_seed_data_populates_every_project_model(self):
        call_command("seed_data", verbosity=0)

        project_apps = {"accounts", "locations", "markets", "catalog", "offers", "orders"}
        empty_models = [
            model._meta.label
            for model in apps.get_models()
            if model._meta.app_label in project_apps
            and model._meta.label not in EPHEMERAL_MODEL_LABELS
            and model.objects.count() == 0
        ]

        self.assertEqual(empty_models, [])
