# Generated for ServiceCity-based order review and courier flow.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_order_service_city(apps, schema_editor):
    Address = apps.get_model("locations", "Address")
    DeliveryArea = apps.get_model("locations", "DeliveryArea")
    Order = apps.get_model("orders", "Order")

    missing_ids = []
    for order in Order.objects.select_related("market"):
        if order.service_city_id:
            continue

        city_id = None
        if order.delivery_address_id:
            city_id = (
                Address.objects.filter(pk=order.delivery_address_id)
                .values_list("service_city_id", flat=True)
                .first()
            )

        if city_id is None:
            city_id = (
                order.market.service_cities.order_by("id")
                .values_list("id", flat=True)
                .first()
            )

        if city_id is None:
            city_id = (
                DeliveryArea.objects.filter(markets=order.market)
                .order_by("id")
                .values_list("service_city_id", flat=True)
                .first()
            )

        if city_id is None:
            missing_ids.append(order.id)
            continue

        order.service_city_id = city_id
        order.save(update_fields=["service_city"])

    if missing_ids:
        raise RuntimeError(
            "Orders must be assigned to a ServiceCity before this migration "
            f"can complete. Missing order IDs: {missing_ids}"
        )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("locations", "0002_servicecity_delivery_price_address_service_city"),
        ("markets", "0002_market_service_cities"),
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("confirmed", "Confirmed"),
                    ("under_preparation", "Under Preparation"),
                    ("ready", "Ready"),
                    ("picked_up", "Picked Up"),
                    ("on_the_way", "On The Way"),
                    ("delivered", "Delivered"),
                    ("failed_delivery", "Failed Delivery"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="service_city",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="orders",
                to="locations.servicecity",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="review_status",
            field=models.CharField(
                choices=[
                    ("pending_review", "Pending Review"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                ],
                default="approved",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="approved_orders",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="rejected_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="rejected_orders",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="rejected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="rejection_reason",
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(backfill_order_service_city, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="order",
            name="service_city",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="orders",
                to="locations.servicecity",
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="review_status",
            field=models.CharField(
                choices=[
                    ("pending_review", "Pending Review"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                ],
                default="pending_review",
                max_length=20,
            ),
        ),
    ]
