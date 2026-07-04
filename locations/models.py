from django.db import models

class ServiceCity(models.Model):
    name = models.CharField(max_length=100)

    center_latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        blank=True,
        null=True,
    )
    center_longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        blank=True,
        null=True,
    )
    radius_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        blank=True,
        null=True,
    )
    delivery_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Address(models.Model):
    class DeliveryType(models.TextChoices):
        FIXED_AREA = "fixed_area", "Fixed area"
        DELIVERY = "delivery", "Delivery"

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="addresses",
    )

    name = models.CharField(max_length=100)  # البيت، الشغل...
    details = models.TextField(blank=True, default="")
    manual_city = models.CharField(max_length=100, blank=True, null=True)
    manual_area = models.CharField(max_length=100, blank=True, null=True)

    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        blank=True,
        null=True,
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        blank=True,
        null=True,
    )
    service_city = models.ForeignKey(
        ServiceCity,
        on_delete=models.PROTECT,
        related_name="addresses",
        blank=True,
        null=True,
    )
    delivery_area = models.ForeignKey(
        "locations.DeliveryArea",
        on_delete=models.PROTECT,
        related_name="addresses",
        blank=True,
        null=True,
    )
    delivery_type = models.CharField(
        max_length=20,
        choices=DeliveryType.choices,
        default=DeliveryType.DELIVERY,
    )

    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(delivery_type="fixed_area")
                        & models.Q(delivery_area__isnull=False)
                    )
                    | (
                        models.Q(delivery_type="delivery")
                        & models.Q(delivery_area__isnull=True)
                    )
                ),
                name="locations_address_delivery_type_valid",
            ),
        ]


class DeliveryArea(models.Model):
    service_city = models.ForeignKey(
        ServiceCity,
        on_delete=models.CASCADE,
        related_name="delivery_areas",
    )

    name = models.CharField(max_length=100)

    center_latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        blank=True,
        null=True,
    )
    center_longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        blank=True,
        null=True,
    )
    radius_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        blank=True,
        null=True,
    )

    delivery_price = models.DecimalField(max_digits=8, decimal_places=2)

    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(delivery_price__gte=0),
                name="locations_delivery_area_price_non_negative",
            ),
            models.UniqueConstraint(
                fields=["service_city", "name"],
                condition=models.Q(is_active=True),
                name="locations_delivery_area_active_name_unique",
            ),
        ]
