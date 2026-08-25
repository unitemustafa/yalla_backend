from django.db import migrations, models


def backfill_product_subcategories(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    through = Product.subcategories.through
    through.objects.bulk_create(
        through(product_id=product_id, storesubcategory_id=subcategory_id)
        for product_id, subcategory_id in Product.objects.values_list(
            "id",
            "subcategory_id",
        ).iterator()
        if subcategory_id is not None
    )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0007_product_archived_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="subcategories",
            field=models.ManyToManyField(
                blank=True,
                related_name="categorized_products",
                to="catalog.storesubcategory",
            ),
        ),
        migrations.RunPython(
            backfill_product_subcategories,
            migrations.RunPython.noop,
        ),
    ]
