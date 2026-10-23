from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

from accounts.models import User
from tools.performance.seed_couriers import seed


class SeedIsolationTests(TestCase):
    def test_courier_seed_refuses_normal_database_before_reading_manifest(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "isolated performance DB"):
            seed()
        self.assertEqual(User.objects.count(), 0)

    def test_seed_refuses_normal_test_database_before_any_writes(self):
        for options in (
            {"users": 1, "counts": "2"},
            {"refresh_tokens": True},
            {"reserve_mobile": True},
        ):
            with (
                self.subTest(options=options),
                self.assertRaisesMessage(CommandError, "outside the isolated"),
            ):
                call_command("seed_performance", stdout=StringIO(), **options)
        self.assertEqual(User.objects.count(), 0)
