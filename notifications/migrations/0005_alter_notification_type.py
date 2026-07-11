from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("notifications", "0004_notification_account_restored_type")]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="type",
            field=models.CharField(
                choices=[
                    ("new_order_review", "New Order Review"),
                    ("order_assigned", "Order Assigned"),
                    ("order_rejected", "Order Rejected"),
                    ("offer_created", "Offer Created"),
                    ("order_created", "Order Created"),
                    ("order_review_approved", "Order Review Approved"),
                    ("order_status_changed", "Order Status Changed"),
                    ("order_cancelled", "Order Cancelled"),
                    ("order_failed_delivery", "Order Failed Delivery"),
                    ("account_disabled", "Account Disabled"),
                    ("account_restored", "Account Restored"),
                    ("courier_availability_changed", "Courier Availability Changed"),
                    ("password_changed", "Password Changed"),
                ],
                max_length=50,
            ),
        ),
    ]
