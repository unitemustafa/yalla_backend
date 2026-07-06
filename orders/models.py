from django.db import models


class Order(models.Model):
    class Scope(models.TextChoices):
        GENERAL = "general", "General"
        SERVICE_CITY = "service_city", "Service city"

    class DeliveryType(models.TextChoices):
        FIXED_AREA = "fixed_area", "Fixed area"
        DELIVERY = "delivery", "Delivery"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        UNDER_PREPARATION = "under_preparation" , "Under Preparation"
        READY = "ready" , "Ready"
        PICKED_UP = "picked_up", "Picked Up"
        ON_THE_WAY = "on_the_way", "On The Way"
        DELIVERED = "delivered", "Delivered"
        FAILED_DELIVERY = "failed_delivery", "Failed Delivery"
        CANCELLED = "cancelled", "Cancelled"

    class ReviewStatus(models.TextChoices):
        PENDING_REVIEW = "pending_review", "Pending Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    delivery_address = models.ForeignKey(
        "locations.Address",
        on_delete=models.PROTECT,
        related_name="orders",
        blank=True,
        null=True,
    )
    assigned_representative = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="assigned_orders",
        blank=True,
        null=True,
    )
    market = models.ForeignKey(
        "markets.Market",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    service_city = models.ForeignKey(
        "locations.ServiceCity",
        on_delete=models.PROTECT,
        related_name="orders",
        blank=True,
        null=True,
    )
    order_scope = models.CharField(
        max_length=20,
        choices=Scope.choices,
        blank=True,
        null=True,
        db_index=True,
    )
    delivery_area = models.ForeignKey(
        "locations.DeliveryArea",
        on_delete=models.PROTECT,
        related_name="orders",
        blank=True,
        null=True,
    )
    delivery_type = models.CharField(
        max_length=20,
        choices=DeliveryType.choices,
        default=DeliveryType.DELIVERY,
    )
    offers = models.ManyToManyField(
        "offers.Offer",
        through="OrderOffer",
        related_name="orders",
        blank=True,
    )
    payment_method = models.CharField(max_length=50)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    review_status = models.CharField(
        max_length=20,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING_REVIEW,
    )
    delivery_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        default=None,
    )
    subtotal_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    image = models.ImageField(upload_to="orders/", blank=True, null=True)
    assigned_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    delivery_note = models.TextField(blank=True)
    delivery_proof = models.ImageField(
        upload_to="delivery-proofs/",
        blank=True,
        null=True,
    )
    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="approved_orders",
        blank=True,
        null=True,
    )
    approved_at = models.DateTimeField(blank=True, null=True)
    rejected_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="rejected_orders",
        blank=True,
        null=True,
    )
    rejected_at = models.DateTimeField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(delivery_price__isnull=True)
                    | models.Q(delivery_price__gte=0)
                ),
                name="orders_order_delivery_price_non_negative",
            ),
            models.CheckConstraint(
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
            models.CheckConstraint(
                condition=(
                    models.Q(order_scope__isnull=True)
                    | (
                        models.Q(order_scope="general")
                        & models.Q(service_city__isnull=True)
                    )
                    | (
                        models.Q(order_scope="service_city")
                        & models.Q(service_city__isnull=False)
                    )
                ),
                name="orders_order_scope_service_city_valid",
            ),
        ]


class OrderMarketSection(models.Model):
    class PickupStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PICKED_UP = "picked_up", "Picked up"

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="market_sections",
    )
    market = models.ForeignKey(
        "markets.Market",
        on_delete=models.PROTECT,
        related_name="order_sections",
    )
    subtotal_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    pickup_status = models.CharField(
        max_length=20,
        choices=PickupStatus.choices,
        default=PickupStatus.PENDING,
    )
    picked_up_at = models.DateTimeField(blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order", "market"],
                name="orders_market_section_order_market_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(subtotal_price__gte=0),
                name="orders_market_section_subtotal_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(discount__gte=0),
                name="orders_market_section_discount_non_negative",
            ),
        ]
        ordering = ("sort_order", "id")


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    section = models.ForeignKey(
        OrderMarketSection,
        on_delete=models.CASCADE,
        related_name="items",
        blank=True,
        null=True,
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    

class OrderOffer(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="order_offers",
    )
    section = models.ForeignKey(
        OrderMarketSection,
        on_delete=models.CASCADE,
        related_name="offers",
        blank=True,
        null=True,
    )
    offer = models.ForeignKey(
        "offers.Offer",
        on_delete=models.PROTECT,
        related_name="order_offers",
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("order", "offer")
