from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("offers", "0007_offeritem"),
    ]

    operations = [
        migrations.AddField(
            model_name="offeritem",
            name="apply_product_discount",
            field=models.BooleanField(default=True),
        ),
    ]
