from django.db import migrations, models


def normalize_order_lifecycle(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    OrderEvent = apps.get_model("orders", "OrderEvent")

    Order.objects.filter(
        status="under_preparation",
        assigned_representative__isnull=True,
    ).update(status="confirmed")
    Order.objects.filter(
        status="under_preparation",
        assigned_representative__isnull=False,
    ).update(status="assigned")
    Order.objects.filter(
        status="ready",
        assigned_representative__isnull=True,
    ).update(status="confirmed")
    Order.objects.filter(
        status="ready",
        assigned_representative__isnull=False,
    ).update(status="assigned")
    Order.objects.filter(
        status="confirmed",
        assigned_representative__isnull=False,
    ).update(status="assigned")
    Order.objects.filter(status="on_the_way").update(status="picked_up")

    event_status_mapping = {
        "under_preparation": "confirmed",
        "ready": "assigned",
        "on_the_way": "picked_up",
    }
    for old_status, new_status in event_status_mapping.items():
        OrderEvent.objects.filter(from_status=old_status).update(
            from_status=new_status,
        )
        OrderEvent.objects.filter(to_status=old_status).update(
            to_status=new_status,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0007_order_event_history"),
    ]

    operations = [
        migrations.RunPython(normalize_order_lifecycle, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("confirmed", "Confirmed"),
                    ("assigned", "Assigned"),
                    ("picked_up", "Picked Up"),
                    ("delivered", "Delivered"),
                    ("failed_delivery", "Failed Delivery"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="orderevent",
            name="from_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("pending", "Pending"),
                    ("confirmed", "Confirmed"),
                    ("assigned", "Assigned"),
                    ("picked_up", "Picked Up"),
                    ("delivered", "Delivered"),
                    ("failed_delivery", "Failed Delivery"),
                    ("cancelled", "Cancelled"),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="orderevent",
            name="to_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("pending", "Pending"),
                    ("confirmed", "Confirmed"),
                    ("assigned", "Assigned"),
                    ("picked_up", "Picked Up"),
                    ("delivered", "Delivered"),
                    ("failed_delivery", "Failed Delivery"),
                    ("cancelled", "Cancelled"),
                ],
                max_length=20,
                null=True,
            ),
        ),
    ]
