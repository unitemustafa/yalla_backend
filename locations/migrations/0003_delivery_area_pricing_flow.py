# Generated for DeliveryArea pricing and address delivery type flow.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("locations", "0002_servicecity_delivery_price_address_service_city"),
    ]

    operations = [
        migrations.AlterField(
            model_name="deliveryarea",
            name="center_latitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=7,
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="deliveryarea",
            name="center_longitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=7,
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="deliveryarea",
            name="radius_km",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=6,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="address",
            name="delivery_area",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="addresses",
                to="locations.deliveryarea",
            ),
        ),
        migrations.AddField(
            model_name="address",
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
        migrations.AddConstraint(
            model_name="address",
            constraint=models.CheckConstraint(
                condition=(
                    (
                        models.Q(delivery_type="fixed_area")
                        & models.Q(delivery_area__isnull=False)
                    )
                    | (
                        models.Q(delivery_type="delivery")
                        & models.Q(delivery_area__isnull=True)
                    )
                ),
                name="locations_address_delivery_type_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="deliveryarea",
            constraint=models.CheckConstraint(
                condition=models.Q(delivery_price__gte=0),
                name="locations_delivery_area_price_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="deliveryarea",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_active=True),
                fields=("service_city", "name"),
                name="locations_delivery_area_active_name_unique",
            ),
        ),
    ]
