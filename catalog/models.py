from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower


class CategoryClassification(models.Model):
    name = models.CharField(max_length=100)


class ProductCategory(models.Model):
    classification = models.ForeignKey(
        CategoryClassification,
        on_delete=models.PROTECT,
        related_name="categories",
    )
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True, null=True)


class StoreSubcategory(models.Model):
    name_ar = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100)
    description_ar = models.TextField(blank=True)
    description_en = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="store-subcategories/",
        blank=True,
        null=True,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name_ar", "id")
        constraints = (
            models.UniqueConstraint(
                Lower("name_ar"),
                name="catalog_store_subcategory_name_ar_ci_unique",
            ),
            models.UniqueConstraint(
                Lower("name_en"),
                name="catalog_store_subcategory_name_en_ci_unique",
            ),
        )

    def __str__(self):
        return self.name_ar


class CategoryAttribute(models.Model):
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.CASCADE,
        related_name="attributes",
    )
    name = models.CharField(max_length=100)


class CategoryOption(models.Model):
    attribute = models.ForeignKey(
        CategoryAttribute,
        on_delete=models.CASCADE,
        related_name="options",
    )
    value = models.CharField(max_length=100)


class Product(models.Model):
    class Theme(models.TextChoices):
        CLOTHING = "clothing", "Clothing"
        CONSUMER = "consumer", "Consumer"
        OTHER = "other", "Other"

    market = models.ForeignKey(
        "markets.Market",
        on_delete=models.CASCADE,
        related_name="products",
    )
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.PROTECT,
        related_name="products",
        blank=True,
        null=True,
    )
    subcategory = models.ForeignKey(
        StoreSubcategory,
        on_delete=models.PROTECT,
        related_name="products",
    )
    theme = models.CharField(
        max_length=20,
        choices=Theme.choices,
        default=Theme.OTHER,
    )
    is_popular = models.BooleanField(default=False)
    is_available = models.BooleanField(
        default=True,
        help_text="True if the product is available for sale."
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    liked_by = models.ManyToManyField(
        "accounts.User",
        related_name="liked_products",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(
        upload_to="products/",
        validators=[
            FileExtensionValidator(
                allowed_extensions=("jpg", "jpeg", "png", "webp")
            )
        ],
    )
    is_primary = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = (
            models.UniqueConstraint(
                fields=("product",),
                condition=Q(is_primary=True),
                name="catalog_one_primary_image_per_product",
            ),
            models.CheckConstraint(
                condition=Q(sort_order__gte=0),
                name="catalog_product_image_sort_order_non_negative",
            ),
        )


class ProductAttributeValue(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="attribute_values",
    )
    attribute = models.ForeignKey(CategoryAttribute, on_delete=models.PROTECT)
    option = models.ForeignKey(CategoryOption, on_delete=models.PROTECT)


class ProductAttribute(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="attributes",
    )
    name = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")


class ProductAttributeOption(models.Model):
    attribute = models.ForeignKey(
        ProductAttribute,
        on_delete=models.CASCADE,
        related_name="options",
    )
    value = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")


class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    sku = models.CharField(max_length=100, blank=True)


class VariantAttributeValue(models.Model):
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="attribute_values",
    )
    attribute = models.ForeignKey(
        CategoryAttribute,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
    )
    option = models.ForeignKey(
        CategoryOption,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
    )
    product_attribute = models.ForeignKey(
        ProductAttribute,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="variant_values",
    )
    product_attribute_option = models.ForeignKey(
        ProductAttributeOption,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="variant_values",
    )


class AdditionClassification(models.Model):
    name = models.CharField(max_length=100)


class ProductAddition(models.Model):
    classification = models.ForeignKey(
        AdditionClassification,
        on_delete=models.PROTECT,
        related_name="additions",
    )
    products = models.ManyToManyField(Product, related_name="additions", blank=True)
    image = models.ImageField(upload_to="additions/", blank=True, null=True)
    name_ar = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
