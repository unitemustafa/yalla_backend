from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.seeders import SeedDataMixin
from orders.models import Order


class Command(SeedDataMixin, BaseCommand):
    help = "Create idempotent fake data for all Yalla project tables."

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()
        users = self._seed_users(now)
        self._seed_otps(users, now)
        areas = self._seed_locations(users)
        self._seed_courier_profiles(users, areas)
        markets = self._seed_markets(areas)
        catalog = self._seed_catalog(markets)
        additions = self._seed_additions(catalog["products"])
        offers = self._seed_offers(markets, catalog["products"], now)
        self._seed_orders(users, markets, catalog["variants"], offers, now)

        self.stdout.write(
            self.style.SUCCESS(
                "Seed data ready. Test password: SeedPass1! "
                "| pending OTP: 123456"
            )
        )
        self.stdout.write(
            "Created/updated: "
            f"{len(users)} users, {len(areas)} delivery areas, "
            f"{len(markets)} markets, {len(catalog['products'])} products, "
            f"{sum(len(value) for value in catalog['variants'].values())} variants, "
            f"{len(additions)} additions, {len(offers)} offers, "
            f"{Order.objects.filter(description__startswith='SEED-ORDER-').count()} orders."
        )
