from django.db import models


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
        on_delete=models.CASCADE,
        related_name="offers",
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

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title