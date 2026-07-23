from django.db import models

class ServiceCity(models.Model):
    name = models.CharField(max_length=100)
    boundary_geojson = models.JSONField(blank=True, null=True)
    boundary_bbox = models.JSONField(blank=True, null=True)

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
    class AddressType(models.TextChoices):
        APARTMENT = "apartment", "Apartment"
        HOUSE = "house", "House"
        OFFICE = "office", "Office"

    class FulfillmentType(models.TextChoices):
        DIRECT = "direct", "Direct delivery"
        EXTERNAL_SHIPPING = "external_shipping", "External shipping"

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
    address_type = models.CharField(
        max_length=20,
        choices=AddressType.choices,
        default=AddressType.APARTMENT,
    )
    recipient_name = models.CharField(max_length=150, blank=True, default="")
    recipient_phone = models.CharField(max_length=30, blank=True, default="")
    street = models.CharField(max_length=255, blank=True, default="")
    building_name = models.CharField(max_length=150, blank=True, default="")
    apartment_number = models.CharField(max_length=50, blank=True, default="")
    floor = models.CharField(max_length=50, blank=True, default="")
    company_name = models.CharField(max_length=150, blank=True, default="")
    additional_instructions = models.TextField(blank=True, default="")
    label = models.CharField(max_length=100, blank=True, default="")
    formatted_address = models.CharField(max_length=500, blank=True, default="")
    place_id = models.CharField(max_length=255, blank=True, default="")
    governorate = models.CharField(max_length=150, blank=True, default="")
    district = models.CharField(max_length=150, blank=True, default="")
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
    fulfillment_type = models.CharField(
        max_length=30,
        choices=FulfillmentType.choices,
        default=FulfillmentType.EXTERNAL_SHIPPING,
        db_index=True,
    )

    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
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
    boundary_geojson = models.JSONField(blank=True, null=True)
    boundary_bbox = models.JSONField(blank=True, null=True)

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
    eta_min_minutes = models.PositiveIntegerField(blank=True, null=True)
    eta_max_minutes = models.PositiveIntegerField(blank=True, null=True)

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
