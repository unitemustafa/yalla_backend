import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0009_shippingcompany"),
        ("orders", "0012_alter_order_delivery_proof_alter_order_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="shipping_company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="orders",
                to="locations.shippingcompany",
            ),
        ),
    ]
