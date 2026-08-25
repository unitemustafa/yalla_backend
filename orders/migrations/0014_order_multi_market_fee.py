from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0013_order_shipping_company"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="multi_market_fee",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="order",
            name="multi_market_fee_rate",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=5),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=models.Q(("multi_market_fee_rate__gte", 0)),
                name="orders_order_multi_market_fee_rate_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=models.Q(("multi_market_fee__gte", 0)),
                name="orders_order_multi_market_fee_non_negative",
            ),
        ),
    ]
