from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_clear_courier_delivery_areas"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="deleted_original_email",
            field=models.EmailField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="deleted_original_username",
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="deleted_original_phone",
            field=models.CharField(blank=True, max_length=30, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="deleted_original_is_active",
            field=models.BooleanField(blank=True, null=True),
        ),
    ]
