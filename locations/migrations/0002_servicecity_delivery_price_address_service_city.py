# Generated for ServiceCity-based order flow.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("locations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicecity",
            name="delivery_price",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AlterField(
            model_name="servicecity",
            name="center_latitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=7,
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="servicecity",
            name="center_longitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=7,
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="servicecity",
            name="radius_km",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=6,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="address",
            name="latitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=7,
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="address",
            name="longitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=7,
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="address",
            name="service_city",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="addresses",
                to="locations.servicecity",
            ),
        ),
    ]
