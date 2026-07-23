from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0005_address_is_active"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicecity",
            name="boundary_geojson",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="servicecity",
            name="boundary_bbox",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deliveryarea",
            name="boundary_geojson",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deliveryarea",
            name="boundary_bbox",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deliveryarea",
            name="eta_min_minutes",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="deliveryarea",
            name="eta_max_minutes",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="address",
            name="address_type",
            field=models.CharField(
                choices=[
                    ("apartment", "Apartment"),
                    ("house", "House"),
                    ("office", "Office"),
                ],
                default="apartment",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="address",
            name="recipient_name",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
        migrations.AddField(
            model_name="address",
            name="recipient_phone",
            field=models.CharField(blank=True, default="", max_length=30),
        ),
        migrations.AddField(
            model_name="address",
            name="street",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="address",
            name="building_name",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
        migrations.AddField(
            model_name="address",
            name="apartment_number",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="address",
            name="floor",
            field=models.CharField(blank=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="address",
            name="company_name",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
        migrations.AddField(
            model_name="address",
            name="additional_instructions",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="address",
            name="label",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="address",
            name="formatted_address",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="address",
            name="place_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="address",
            name="governorate",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
        migrations.AddField(
            model_name="address",
            name="district",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
        migrations.AddField(
            model_name="address",
            name="fulfillment_type",
            field=models.CharField(
                choices=[
                    ("direct", "Direct delivery"),
                    ("external_shipping", "External shipping"),
                ],
                db_index=True,
                default="external_shipping",
                max_length=30,
            ),
        ),
    ]
