"""Upgrade historical data without deleting outbox rows or changing addresses."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from rest_framework.test import APITransactionTestCase

from notifications.models import LegacyPushOutbox
from . import tests as fixtures
from .models import Order


class ReleaseMigrationTests(APITransactionTestCase):
    def test_upgrade_preserves_legacy_outbox_and_backfills_address(self):
        fixtures.OrderAPITests.setUp(self)
        self.address.street = "Historical instructions"
        self.address.save(update_fields=["street"])
        order = Order.objects.create(
            user=self.customer, market=self.market, delivery_address=self.address
        )
        legacy = LegacyPushOutbox.objects.create(
            kind="account_disabled",
            user=self.customer,
            options={"preserve": "legacy pending work"},
        )
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        executor.migrate(
            [
                (
                    "orders",
                    "0016_order_client_request_hash_order_client_request_key_and_more",
                ),
                ("notifications", "0014_remove_pushoutbox_state"),
            ]
        )
        MigrationExecutor(connection).migrate(latest)
        retained = LegacyPushOutbox.objects.get(pk=legacy.pk)
        self.assertEqual(retained.options, {"preserve": "legacy pending work"})
        order.refresh_from_db()
        self.assertEqual(
            order.delivery_address_snapshot["street"], "Historical instructions"
        )
        self.address.street = "New address book instructions"
        self.address.save(update_fields=["street"])
        order.refresh_from_db()
        self.assertEqual(
            order.delivery_address_snapshot["street"], "Historical instructions"
        )
