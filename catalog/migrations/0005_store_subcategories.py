import django.db.models.deletion
from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0004_productimage"),
    ]

    operations = [
        migrations.CreateModel(
            name="StoreSubcategory",
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
                ("name_ar", models.CharField(max_length=100)),
                ("name_en", models.CharField(max_length=100)),
                ("description_ar", models.TextField(blank=True)),
                ("description_en", models.TextField(blank=True)),
                (
                    "image",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to="store-subcategories/",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("name_ar", "id"),
                "constraints": (
                    models.UniqueConstraint(
                        Lower("name_ar"),
                        name="catalog_store_subcategory_name_ar_ci_unique",
                    ),
                    models.UniqueConstraint(
                        Lower("name_en"),
                        name="catalog_store_subcategory_name_en_ci_unique",
                    ),
                ),
            },
        ),
        migrations.AddField(
            model_name="product",
            name="subcategory",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="products",
                to="catalog.storesubcategory",
            ),
        ),
    ]
