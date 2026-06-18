from django.db import models


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
    market = models.ForeignKey(
        "markets.Market",
        on_delete=models.CASCADE,
        related_name="products",
    )
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.PROTECT,
        related_name="products",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ProductAttributeValue(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="attribute_values",
    )
    attribute = models.ForeignKey(CategoryAttribute, on_delete=models.PROTECT)
    option = models.ForeignKey(CategoryOption, on_delete=models.PROTECT)


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
    attribute = models.ForeignKey(CategoryAttribute, on_delete=models.PROTECT)
    option = models.ForeignKey(CategoryOption, on_delete=models.PROTECT)


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