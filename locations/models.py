from django.db import models

# Create your models here.

class DeliveryArea(models.Model):
    name = models.CharField(max_length=100)

    delivery_price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True
    )

    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)