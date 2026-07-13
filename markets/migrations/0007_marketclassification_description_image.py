from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("markets", "0006_market_description_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="marketclassification",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="marketclassification",
            name="image",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="market-classifications/",
            ),
        ),
    ]
