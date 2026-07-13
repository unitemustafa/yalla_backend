from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0008_delivery_area_notification_dispatch"),
        ("notifications", "0008_product_notifications"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="type",
            field=models.CharField(
                choices=[
                    ("new_order_review", "New Order Review"),
                    ("order_assigned", "Order Assigned"),
                    ("order_unassigned", "Order Unassigned"),
                    ("order_rejected", "Order Rejected"),
                    ("offer_created", "Offer Created"),
                    ("product_created", "Product Created"),
                    ("order_created", "Order Created"),
                    ("order_review_approved", "Order Review Approved"),
                    ("order_status_changed", "Order Status Changed"),
                    ("order_cancelled", "Order Cancelled"),
                    ("order_failed_delivery", "Order Failed Delivery"),
                    ("account_disabled", "Account Disabled"),
                    ("account_restored", "Account Restored"),
                    ("delivery_area_created", "Delivery Area Created"),
                    (
                        "courier_availability_changed",
                        "Courier Availability Changed",
                    ),
                    ("courier_profile_updated", "Courier Profile Updated"),
                    ("password_changed", "Password Changed"),
                ],
                max_length=50,
            ),
        ),
    ]
