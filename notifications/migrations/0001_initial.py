# Generated for order review and courier assignment notifications.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orders", "0002_servicecity_review_flow"),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
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
                    "audience",
                    models.CharField(
                        choices=[
                            ("admin", "Admin"),
                            ("courier", "Courier"),
                            ("client", "Client"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("new_order_review", "New Order Review"),
                            ("order_assigned", "Order Assigned"),
                            ("order_rejected", "Order Rejected"),
                        ],
                        max_length=50,
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("message", models.TextField()),
                ("is_read", models.BooleanField(default=False)),
                ("is_blocking", models.BooleanField(default=False)),
                ("is_resolved", models.BooleanField(default=False)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to="orders.order",
                    ),
                ),
                (
                    "recipient",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["audience", "type", "is_read"],
                        name="notificatio_audienc_6989fc_idx",
                    ),
                    models.Index(
                        fields=["audience", "is_blocking", "is_resolved"],
                        name="notificatio_audienc_2d2c08_idx",
                    ),
                    models.Index(
                        fields=["recipient", "is_read"],
                        name="notificatio_recipie_4e3567_idx",
                    ),
                ],
            },
        ),
    ]
