from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0006_location_polygons_and_structured_addresses"),
    ]

    operations = [
        migrations.AddField(
            model_name="deliveryarea",
            name="boundary_source",
            field=models.CharField(
                choices=[
                    ("osm", "OpenStreetMap"),
                    ("h3", "H3 cells"),
                    ("manual", "Manual"),
                ],
                default="manual",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="deliveryarea",
            name="h3_cells",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deliveryarea",
            name="h3_resolution",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deliveryarea",
            name="source_reference",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
