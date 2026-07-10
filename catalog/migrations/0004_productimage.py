import django.core.validators
import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


def copy_legacy_product_images(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    ProductImage = apps.get_model("catalog", "ProductImage")

    products = Product.objects.exclude(image__isnull=True).exclude(image="")
    for product in products.iterator():
        if ProductImage.objects.filter(product_id=product.id).exists():
            continue
        ProductImage.objects.create(
            product_id=product.id,
            image=str(product.image),
            is_primary=True,
            sort_order=0,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0003_product_theme_product_attributes"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductImage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "image",
                    models.ImageField(
                        upload_to="products/",
                        validators=[
                            django.core.validators.FileExtensionValidator(
                                allowed_extensions=("jpg", "jpeg", "png", "webp")
                            )
                        ],
                    ),
                ),
                ("is_primary", models.BooleanField(default=False)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="images",
                        to="catalog.product",
                    ),
                ),
            ],
            options={
                "ordering": ("sort_order", "id"),
                "constraints": (
                    models.UniqueConstraint(
                        condition=Q(is_primary=True),
                        fields=("product",),
                        name="catalog_one_primary_image_per_product",
                    ),
                    models.CheckConstraint(
                        condition=Q(sort_order__gte=0),
                        name="catalog_product_image_sort_order_non_negative",
                    ),
                ),
            },
        ),
        migrations.RunPython(
            copy_legacy_product_images,
            migrations.RunPython.noop,
        ),
    ]
