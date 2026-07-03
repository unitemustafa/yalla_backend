# Generated for ServiceCity-based order flow.

from django.db import migrations, models


def copy_delivery_area_cities(apps, schema_editor):
    Market = apps.get_model("markets", "Market")
    for market in Market.objects.all():
        city_ids = (
            market.delivery_areas.order_by("service_city_id")
            .values_list("service_city_id", flat=True)
            .distinct()
        )
        market.service_cities.add(*city_ids)


class Migration(migrations.Migration):

    dependencies = [
        ("locations", "0002_servicecity_delivery_price_address_service_city"),
        ("markets", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="market",
            name="service_cities",
            field=models.ManyToManyField(
                blank=True,
                related_name="markets",
                to="locations.servicecity",
            ),
        ),
        migrations.RunPython(copy_delivery_area_cities, migrations.RunPython.noop),
    ]
