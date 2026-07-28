from decimal import Decimal

from django.db import models
from django.db.models import Count, DecimalField, Exists, ExpressionWrapper, F, Min, OuterRef, Q, Value
from django.db.models.functions import Lower


class MarketQuerySet(models.QuerySet):
    def with_client_metrics(self, user=None):
        payable_price = ExpressionWrapper(
            F("products__variants__price")
            * (Value(Decimal("100.00")) - F("products__discount"))
            / Value(Decimal("100.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        visible_products = Q(
            products__archived_at__isnull=True,
            products__is_available=True,
            products__variants__isnull=False,
        )
        annotations = {
            "product_count": Count(
                "products",
                filter=visible_products,
                distinct=True,
            ),
            "minimum_product_price": Min(
                payable_price,
                filter=visible_products,
            ),
        }
        if user is not None and getattr(user, "is_authenticated", False):
            liked_through = self.model.liked_by.through
            annotations["is_liked"] = Exists(
                liked_through.objects.filter(
                    market_id=OuterRef("pk"),
                    user_id=user.pk,
                )
            )
        else:
            annotations["is_liked"] = Value(False)
        return self.annotate(**annotations)


class MarketClassification(models.Model):
    class ClassificationType(models.TextChoices):
        POPULAR = "popular", "Popular"
        FEATURED = "featured", "Featured"
        NORMAL = "normal", "Normal"

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="market-classifications/",
        blank=True,
        null=True,
    )
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


class MarketType(models.Model):
    classification = models.ForeignKey(
        MarketClassification,
        on_delete=models.CASCADE,
        related_name="market_types",
    )
    name_ar = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100)
    image = models.ImageField(upload_to="market-types/")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = (
            models.UniqueConstraint(
                Lower("name_ar"),
                "classification",
                name="markets_market_type_name_ar_ci_unique",
            ),
            models.UniqueConstraint(
                Lower("name_en"),
                "classification",
                name="markets_market_type_name_en_ci_unique",
            ),
        )

    def __str__(self):
        return self.name_ar


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
    cover_image = models.ImageField(
        upload_to="markets/covers/",
        blank=True,
        null=True,
    )
    delivery_time_min_minutes = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
    )
    delivery_time_max_minutes = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
    )
    branch = models.CharField(max_length=255, blank=True)
    scope = models.CharField(
        max_length=20,
        choices=Scope.choices,
        default=Scope.SERVICE_CITY,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    is_popular = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(blank=True, null=True, db_index=True)

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
    subcategories = models.ManyToManyField(
        "catalog.StoreSubcategory",
        through="MarketSubcategory",
        related_name="markets",
        blank=True,
    )
    market_types = models.ManyToManyField(
        MarketType,
        related_name="markets",
        blank=True,
    )
    liked_by = models.ManyToManyField(
        "accounts.User",
        related_name="liked_markets",
        blank=True,
    )

    objects = MarketQuerySet.as_manager()

    class Meta:
        constraints = (
            models.CheckConstraint(
                condition=(
                    (
                        Q(delivery_time_min_minutes__isnull=True)
                        & Q(delivery_time_max_minutes__isnull=True)
                    )
                    | (
                        Q(delivery_time_min_minutes__gt=0)
                        & Q(delivery_time_max_minutes__gt=0)
                        & Q(
                            delivery_time_max_minutes__gte=F(
                                "delivery_time_min_minutes"
                            )
                        )
                    )
                ),
                name="markets_market_delivery_time_valid",
            ),
        )

    def __str__(self):
        return self.name

    def get_deletion_mode(self):
        annotated_mode = getattr(self, "deletion_mode_is_archive", None)
        if annotated_mode is not None:
            return "archive" if annotated_mode else "delete"
        if self.orders.exists() or self.order_sections.exists():
            return "archive"
        protected_products = self.products.filter(
            models.Q(variants__order_items__isnull=False)
            | models.Q(variants__offer_items__isnull=False)
        )
        return "archive" if protected_products.exists() else "delete"


class MarketSubcategory(models.Model):
    market = models.ForeignKey(
        Market,
        on_delete=models.CASCADE,
        related_name="subcategory_assignments",
    )
    subcategory = models.ForeignKey(
        "catalog.StoreSubcategory",
        on_delete=models.CASCADE,
        related_name="market_assignments",
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = (
            models.UniqueConstraint(
                fields=("market", "subcategory"),
                name="markets_market_subcategory_unique",
            ),
        )
