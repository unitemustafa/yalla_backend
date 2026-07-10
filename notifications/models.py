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
        OFFER_CREATED = "offer_created", "Offer Created"
        ORDER_CREATED = "order_created", "Order Created"
        ORDER_REVIEW_APPROVED = "order_review_approved", "Order Review Approved"
        ORDER_STATUS_CHANGED = "order_status_changed", "Order Status Changed"
        ORDER_CANCELLED = "order_cancelled", "Order Cancelled"
        ORDER_FAILED_DELIVERY = "order_failed_delivery", "Order Failed Delivery"

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
    order_event = models.ForeignKey(
        "orders.OrderEvent",
        on_delete=models.SET_NULL,
        related_name="notifications",
        blank=True,
        null=True,
    )
    offer = models.ForeignKey(
        "offers.Offer",
        on_delete=models.SET_NULL,
        related_name="notifications",
        blank=True,
        null=True,
    )
    data = models.JSONField(default=dict, blank=True)
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
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "offer"],
                condition=models.Q(type="offer_created", offer__isnull=False),
                name="notifications_offer_recipient_unique",
            ),
            models.UniqueConstraint(
                fields=["recipient", "order_event"],
                condition=models.Q(order_event__isnull=False),
                name="notifications_order_event_recipient_unique",
            ),
        ]

    def __str__(self):
        return self.title


class ClientDevice(models.Model):
    class Platform(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="client_devices",
    )
    token = models.CharField(max_length=512, unique=True)
    platform = models.CharField(max_length=20, choices=Platform.choices)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["user", "is_active"])]
