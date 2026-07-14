from django.db import models
from django.utils import timezone


class Offer(models.Model):
    class OfferType(models.TextChoices):
        PACKAGE = "package", "Package"
        FLASH = "flash", "Flash"
        DISCOUNT = "discount", "Discount"
        ANNOUNCEMENT = "announcement" , "Announcement"
        DELIVERY = "delivery" , "Delivery"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        EXPIRED = "expired", "Expired"

    market = models.ForeignKey(
        "markets.Market",
        on_delete=models.SET_NULL,
        related_name="offers",
        blank=True,
        null=True,
    )
    show_in_general = models.BooleanField(default=False)
    service_cities = models.ManyToManyField(
        "locations.ServiceCity",
        related_name="offers",
        blank=True,
    )

    products = models.ManyToManyField(
        "catalog.Product",
        related_name="offers",
        blank=True,
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="offers/", blank=True, null=True)

    type = models.CharField(
        max_length=30,
        choices=OfferType.choices,
        default=OfferType.PACKAGE,
    )

    discount = models.DecimalField(max_digits=10, decimal_places=2)

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    active_days = models.JSONField(default=list, blank=True)
    use_limits = models.PositiveIntegerField(null=True, blank=True)
    user_limit = models.PositiveIntegerField(null=True, blank=True)
    announcement_url = models.URLField(blank=True, default="")
    announcement_cta_label = models.CharField(max_length=80, blank=True, default="")
    announcement_priority = models.PositiveSmallIntegerField(default=0)
    announcement_display_seconds = models.PositiveSmallIntegerField(default=15)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    send_push_notification = models.BooleanField(default=False)
    push_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def get_effective_status(self, now=None):
        now = now or timezone.now()
        if self.status == self.Status.INACTIVE:
            return self.Status.INACTIVE
        if self.end_time <= now:
            return self.Status.EXPIRED
        if self.start_time > now:
            return "scheduled"
        return self.Status.ACTIVE

    def has_valid_visibility_scope(self):
        active_cities = self.service_cities.filter(is_active=True).count()
        return active_cities == 0 if self.show_in_general else active_cities == 1

    def has_active_markets(self):
        from markets.models import Market

        if self.market_id and self.market.status != Market.Status.ACTIVE:
            return False
        return not self.products.exclude(market__status=Market.Status.ACTIVE).exists()

    def is_currently_visible(self, now=None):
        return self.get_effective_status(now) == self.Status.ACTIVE and self.has_valid_visibility_scope()

    def can_send_notification(self, now=None):
        return self.is_currently_visible(now) and self.has_active_markets()


class OfferItem(models.Model):
    offer = models.ForeignKey(
        Offer,
        on_delete=models.CASCADE,
        related_name="items",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="offer_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    apply_product_discount = models.BooleanField(default=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(
                fields=("offer", "variant"),
                name="unique_offer_variant",
            ),
        ]

    def __str__(self):
        return f"{self.offer} - {self.variant} x{self.quantity}"
