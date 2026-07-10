from django.db import models


class MarketClassification(models.Model):
    class ClassificationType(models.TextChoices):
        POPULAR = "popular", "Popular"
        FEATURED = "featured", "Featured"
        NORMAL = "normal", "Normal"

    name = models.CharField(max_length=100)
    classification_type = models.CharField(
        max_length=20,
        choices=ClassificationType.choices,
        default=ClassificationType.NORMAL,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    classification_type__in=[
                        "popular",
                        "featured",
                        "normal",
                    ]
                ),
                name="markets_market_classification_type_valid",
            ),
        ]

    def __str__(self):
        return self.name


class Market(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    class Scope(models.TextChoices):
        GENERAL = "general", "General"
        SERVICE_CITY = "service_city", "Service city"

    classification = models.ForeignKey(
        MarketClassification,
        on_delete=models.PROTECT,
        related_name="markets",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="markets/", blank=True, null=True)
    branch = models.CharField(max_length=255, blank=True)
    scope = models.CharField(
        max_length=20,
        choices=Scope.choices,
        default=Scope.SERVICE_CITY,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    delivery_areas = models.ManyToManyField(
        "locations.DeliveryArea",
        related_name="markets",
        blank=True,
    )
    service_cities = models.ManyToManyField(
        "locations.ServiceCity",
        related_name="markets",
        blank=True,
    )

    def __str__(self):
        return self.name
