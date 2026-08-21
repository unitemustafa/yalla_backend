import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0012_partner_application_approved"),
        ("locations", "0008_servicecity_archived_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PushOutbox",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("notification", "Notification"),
                            ("courier_notification", "Courier notification"),
                            ("account_restored", "Account restored"),
                            ("account_disabled", "Account disabled"),
                            ("delivery_area_status", "Delivery area status"),
                        ],
                        max_length=32,
                    ),
                ),
                ("options", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("available_at", models.DateTimeField(auto_now_add=True)),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "delivery_area",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="push_outbox_entries",
                        to="locations.deliveryarea",
                    ),
                ),
                (
                    "notification",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="push_outbox_entries",
                        to="notifications.notification",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="push_outbox_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["status", "available_at"],
                        name="notificatio_status_91b957_idx",
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("delivery_area__isnull", True),
                                ("kind", "account_disabled"),
                                ("notification__isnull", True),
                                ("user__isnull", False),
                            ),
                            models.Q(
                                ("delivery_area__isnull", True),
                                ("kind__in", (
                                    "notification",
                                    "courier_notification",
                                    "account_restored",
                                )),
                                ("notification__isnull", False),
                                ("user__isnull", True),
                            ),
                            models.Q(
                                ("delivery_area__isnull", False),
                                ("kind", "delivery_area_status"),
                                ("notification__isnull", True),
                                ("user__isnull", True),
                            ),
                            _connector="OR",
                        ),
                        name="notifications_push_outbox_target_valid",
                    )
                ],
            },
        ),
    ]
