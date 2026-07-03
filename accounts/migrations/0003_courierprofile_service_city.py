# Generated for ServiceCity-based courier assignment.

import django.db.models.deletion
from django.db import migrations, models


def backfill_courier_service_city(apps, schema_editor):
    CourierProfile = apps.get_model("accounts", "CourierProfile")
    missing_ids = []
    for profile in CourierProfile.objects.select_related("delivery_area"):
        if profile.service_city_id:
            continue
        if profile.delivery_area_id:
            profile.service_city_id = profile.delivery_area.service_city_id
            profile.save(update_fields=["service_city"])
            continue
        missing_ids.append(profile.id)
    if missing_ids:
        raise RuntimeError(
            "Courier profiles must be assigned to a ServiceCity before this "
            f"migration can complete. Missing profile IDs: {missing_ids}"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_initial"),
        ("locations", "0002_servicecity_delivery_price_address_service_city"),
    ]

    operations = [
        migrations.AlterField(
            model_name="courierprofile",
            name="delivery_area",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="courier_profiles",
                to="locations.deliveryarea",
            ),
        ),
        migrations.AddField(
            model_name="courierprofile",
            name="service_city",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="courier_profiles",
                to="locations.servicecity",
            ),
        ),
        migrations.RunPython(backfill_courier_service_city, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="courierprofile",
            name="service_city",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="courier_profiles",
                to="locations.servicecity",
            ),
        ),
    ]
