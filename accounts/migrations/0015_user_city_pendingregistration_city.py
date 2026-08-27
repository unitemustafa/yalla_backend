from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0014_pendingregistration"),
    ]

    operations = [
        migrations.AddField(
            model_name="pendingregistration",
            name="city",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="user",
            name="city",
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
