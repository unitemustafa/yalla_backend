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
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="addresses",
    )

    name = models.CharField(max_length=100)  # البيت، الشغل...
    details = models.TextField(blank=True, default="")

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

    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class DeliveryArea(models.Model):
    service_city = models.ForeignKey(
        ServiceCity,
        on_delete=models.CASCADE,
        related_name="delivery_areas",
    )

    name = models.CharField(max_length=100)

    center_latitude = models.DecimalField(max_digits=10, decimal_places=7)
    center_longitude = models.DecimalField(max_digits=10, decimal_places=7)
    radius_km = models.DecimalField(max_digits=6, decimal_places=2)

    delivery_price = models.DecimalField(max_digits=8, decimal_places=2)

    is_active = models.BooleanField(default=True)
