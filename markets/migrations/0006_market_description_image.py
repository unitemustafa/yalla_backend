from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("markets", "0005_marketclassification_is_active"),
    ]

    operations = [
        migrations.AddField(
            model_name="market",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="market",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="markets/"),
        ),
    ]
