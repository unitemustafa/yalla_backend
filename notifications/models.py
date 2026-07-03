from django.db import models


class Notification(models.Model):
    class Audience(models.TextChoices):
        ADMIN = "admin", "Admin"
        COURIER = "courier", "Courier"
        CLIENT = "client", "Client"

    class Type(models.TextChoices):
        NEW_ORDER_REVIEW = "new_order_review", "New Order Review"
        ORDER_ASSIGNED = "order_assigned", "Order Assigned"
        ORDER_REJECTED = "order_rejected", "Order Rejected"

    audience = models.CharField(max_length=30, choices=Audience.choices)
    type = models.CharField(max_length=50, choices=Type.choices)
    title = models.CharField(max_length=255)
    message = models.TextField()
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="notifications",
        blank=True,
        null=True,
    )
    recipient = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="notifications",
        blank=True,
        null=True,
    )
    is_read = models.BooleanField(default=False)
    is_blocking = models.BooleanField(default=False)
    is_resolved = models.BooleanField(default=False)
    read_at = models.DateTimeField(blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["audience", "type", "is_read"]),
            models.Index(fields=["audience", "is_blocking", "is_resolved"]),
            models.Index(fields=["recipient", "is_read"]),
        ]

    def __str__(self):
        return self.title
