# Generated manually for the product theme/product-owned attributes migration.

import django.db.models.deletion
from django.db import migrations, models


def forwards_copy_legacy_attributes(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    ProductAttribute = apps.get_model("catalog", "ProductAttribute")
    ProductAttributeOption = apps.get_model("catalog", "ProductAttributeOption")
    VariantAttributeValue = apps.get_model("catalog", "VariantAttributeValue")

    for product in Product.objects.select_related("category").order_by("id"):
        option_map = {}
        category = product.category
        if category is not None:
            legacy_attributes = category.attributes.prefetch_related("options").order_by("id")
            for attr_index, legacy_attribute in enumerate(legacy_attributes):
                product_attribute = ProductAttribute.objects.create(
                    product=product,
                    name=legacy_attribute.name,
                    sort_order=attr_index,
                )
                for option_index, legacy_option in enumerate(
                    legacy_attribute.options.order_by("id")
                ):
                    product_option = ProductAttributeOption.objects.create(
                        attribute=product_attribute,
                        value=legacy_option.value,
                        sort_order=option_index,
                    )
                    option_map[(legacy_attribute.id, legacy_option.id)] = (
                        product_attribute.id,
                        product_option.id,
                    )

        for value in VariantAttributeValue.objects.filter(
            variant__product_id=product.id,
            attribute_id__isnull=False,
            option_id__isnull=False,
        ):
            mapped = option_map.get((value.attribute_id, value.option_id))
            if mapped is None:
                continue
            value.product_attribute_id = mapped[0]
            value.product_attribute_option_id = mapped[1]
            value.save(
                update_fields=[
                    "product_attribute_id",
                    "product_attribute_option_id",
                ]
            )


def reverse_clear_product_attributes(apps, schema_editor):
    ProductAttribute = apps.get_model("catalog", "ProductAttribute")
    VariantAttributeValue = apps.get_model("catalog", "VariantAttributeValue")
    VariantAttributeValue.objects.update(
        product_attribute_id=None,
        product_attribute_option_id=None,
    )
    ProductAttribute.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0002_product_liked_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="is_popular",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="product",
            name="theme",
            field=models.CharField(
                choices=[
                    ("clothing", "Clothing"),
                    ("consumer", "Consumer"),
                    ("other", "Other"),
                ],
                default="other",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="product",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="products",
                to="catalog.productcategory",
            ),
        ),
        migrations.CreateModel(
            name="ProductAttribute",
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
                ("name", models.CharField(max_length=100)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attributes",
                        to="catalog.product",
                    ),
                ),
            ],
            options={
                "ordering": ("sort_order", "id"),
            },
        ),
        migrations.CreateModel(
            name="ProductAttributeOption",
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
                ("value", models.CharField(max_length=100)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                (
                    "attribute",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="options",
                        to="catalog.productattribute",
                    ),
                ),
            ],
            options={
                "ordering": ("sort_order", "id"),
            },
        ),
        migrations.AlterField(
            model_name="variantattributevalue",
            name="attribute",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="catalog.categoryattribute",
            ),
        ),
        migrations.AlterField(
            model_name="variantattributevalue",
            name="option",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="catalog.categoryoption",
            ),
        ),
        migrations.AddField(
            model_name="variantattributevalue",
            name="product_attribute",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="variant_values",
                to="catalog.productattribute",
            ),
        ),
        migrations.AddField(
            model_name="variantattributevalue",
            name="product_attribute_option",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="variant_values",
                to="catalog.productattributeoption",
            ),
        ),
        migrations.RunPython(
            forwards_copy_legacy_attributes,
            reverse_clear_product_attributes,
        ),
    ]
