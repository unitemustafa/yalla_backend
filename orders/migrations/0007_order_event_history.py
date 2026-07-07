from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_order_events(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    OrderEvent = apps.get_model("orders", "OrderEvent")

    events = []
    for order in Order.objects.order_by("id").iterator():
        events.append(
            OrderEvent(
                order_id=order.id,
                event_type="order_created",
                from_status=None,
                to_status=order.status,
                actor_id=None,
                note="",
                metadata={"backfilled": True},
                created_at=order.created_at,
            )
        )
    OrderEvent.objects.bulk_create(events, batch_size=500)


def remove_backfilled_order_events(apps, schema_editor):
    OrderEvent = apps.get_model("orders", "OrderEvent")
    OrderEvent.objects.filter(
        event_type="order_created",
        metadata__backfilled=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orders", "0006_allow_manual_delivery_price"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrderEvent",
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
                    "event_type",
                    models.CharField(
                        choices=[
                            ("order_created", "Order created"),
                            ("review_approved", "Review approved"),
                            ("review_rejected", "Review rejected"),
                            ("status_changed", "Status changed"),
                            ("assigned", "Assigned"),
                            ("unassigned", "Unassigned"),
                            (
                                "delivery_price_changed",
                                "Delivery price changed",
                            ),
                            ("cancelled", "Cancelled"),
                        ],
                        max_length=40,
                    ),
                ),
                (
                    "from_status",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("pending", "Pending"),
                            ("confirmed", "Confirmed"),
                            ("under_preparation", "Under Preparation"),
                            ("ready", "Ready"),
                            ("picked_up", "Picked Up"),
                            ("on_the_way", "On The Way"),
                            ("delivered", "Delivered"),
                            ("failed_delivery", "Failed Delivery"),
                            ("cancelled", "Cancelled"),
                        ],
                        max_length=20,
                        null=True,
                    ),
                ),
                (
                    "to_status",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("pending", "Pending"),
                            ("confirmed", "Confirmed"),
                            ("under_preparation", "Under Preparation"),
                            ("ready", "Ready"),
                            ("picked_up", "Picked Up"),
                            ("on_the_way", "On The Way"),
                            ("delivered", "Delivered"),
                            ("failed_delivery", "Failed Delivery"),
                            ("cancelled", "Cancelled"),
                        ],
                        max_length=20,
                        null=True,
                    ),
                ),
                ("note", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="order_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="history_events",
                        to="orders.order",
                    ),
                ),
            ],
            options={
                "ordering": ("created_at", "id"),
            },
        ),
        migrations.AddIndex(
            model_name="orderevent",
            index=models.Index(
                fields=["order", "created_at", "id"],
                name="orders_orde_order_i_3a0c4d_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="orderevent",
            index=models.Index(
                fields=["event_type"],
                name="orders_orde_event_t_2ba24d_idx",
            ),
        ),
        migrations.RunPython(
            backfill_order_events,
            remove_backfilled_order_events,
        ),
    ]
