# Generated for DeliveryArea-based order delivery pricing.

import django.db.models.deletion
from django.db import migrations, models


def backfill_order_delivery_fields(apps, schema_editor):
    Address = apps.get_model("locations", "Address")
    Order = apps.get_model("orders", "Order")

    for order in Order.objects.all().only(
        "id",
        "delivery_address_id",
        "delivery_area_id",
        "delivery_type",
        "delivery_price",
    ):
        delivery_type = "delivery"
        delivery_area_id = None
        delivery_price = None

        if order.delivery_address_id:
            address = (
                Address.objects.filter(pk=order.delivery_address_id)
                .select_related("delivery_area")
                .first()
            )
            if (
                address is not None
                and address.delivery_type == "fixed_area"
                and address.delivery_area_id
            ):
                delivery_type = "fixed_area"
                delivery_area_id = address.delivery_area_id
                delivery_price = address.delivery_area.delivery_price

        order.delivery_type = delivery_type
        order.delivery_area_id = delivery_area_id
        order.delivery_price = delivery_price
        order.save(
            update_fields=[
                "delivery_type",
                "delivery_area",
                "delivery_price",
            ]
        )


def restore_nullable_delivery_prices(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    Order.objects.filter(delivery_price__isnull=True).update(delivery_price=0)


class Migration(migrations.Migration):

    dependencies = [
        ("locations", "0003_delivery_area_pricing_flow"),
        ("orders", "0002_servicecity_review_flow"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="delivery_area",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="orders",
                to="locations.deliveryarea",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="delivery_type",
            field=models.CharField(
                choices=[
                    ("fixed_area", "Fixed area"),
                    ("delivery", "Delivery"),
                ],
                default="delivery",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="delivery_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=None,
                max_digits=10,
                null=True,
            ),
        ),
        migrations.RunPython(
            backfill_order_delivery_fields,
            restore_nullable_delivery_prices,
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(delivery_price__isnull=True)
                    | models.Q(delivery_price__gte=0)
                ),
                name="orders_order_delivery_price_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=(
                    (
                        models.Q(delivery_type="fixed_area")
                        & models.Q(delivery_area__isnull=False)
                        & models.Q(delivery_price__isnull=False)
                    )
                    | (
                        models.Q(delivery_type="delivery")
                        & models.Q(delivery_area__isnull=True)
                        & models.Q(delivery_price__isnull=True)
                    )
                ),
                name="orders_order_delivery_type_valid",
            ),
        ),
    ]
