from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("markets", "0007_marketclassification_description_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="market",
            name="is_popular",
            field=models.BooleanField(default=False),
        ),
    ]
