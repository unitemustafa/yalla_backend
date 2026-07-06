from django.db import migrations


def clear_courier_delivery_areas(apps, schema_editor):
    CourierProfile = apps.get_model("accounts", "CourierProfile")
    CourierProfile.objects.filter(delivery_area__isnull=False).update(
        delivery_area=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_otpcooldown"),
    ]

    operations = [
        migrations.RunPython(clear_courier_delivery_areas, migrations.RunPython.noop),
    ]
