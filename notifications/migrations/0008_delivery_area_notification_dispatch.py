import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("locations", "0005_address_is_active"),
        ("notifications", "0007_offernotificationdispatch_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="DeliveryAreaNotificationDispatch",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("recipient_count", models.PositiveIntegerField(default=0)),
                ("notification_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "delivery_area",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notification_dispatch",
                        to="locations.deliveryarea",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="notification",
            name="delivery_area_dispatch",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="notifications",
                to="notifications.deliveryareanotificationdispatch",
            ),
        ),
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
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(
                condition=models.Q(delivery_area_dispatch__isnull=False),
                fields=("delivery_area_dispatch", "recipient"),
                name="notifications_area_dispatch_recipient_unique",
            ),
        ),
    ]
