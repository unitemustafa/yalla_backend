from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0005_multi_market_parent_orders"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="order",
            name="orders_order_delivery_type_valid",
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=(
                    (
                        models.Q(delivery_type="fixed_area")
                        & models.Q(delivery_area__isnull=False)
                        & models.Q(delivery_price__isnull=False)
                    )
                    | (
                        models.Q(delivery_type="delivery")
                        & models.Q(delivery_area__isnull=True)
                    )
                ),
                name="orders_order_delivery_type_valid",
            ),
        ),
    ]
