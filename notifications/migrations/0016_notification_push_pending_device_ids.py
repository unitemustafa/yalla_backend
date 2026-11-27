from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0015_legacypushoutbox"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="push_pending_device_ids",
            field=models.JSONField(blank=True, editable=False, null=True),
        ),
    ]
