import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0005_store_subcategories"),
        ("markets", "0008_market_is_popular"),
    ]

    operations = [
        migrations.CreateModel(
            name="MarketSubcategory",
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
                ("sort_order", models.PositiveIntegerField(default=0)),
                (
                    "market",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subcategory_assignments",
                        to="markets.market",
                    ),
                ),
                (
                    "subcategory",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="market_assignments",
                        to="catalog.storesubcategory",
                    ),
                ),
            ],
            options={
                "ordering": ("sort_order", "id"),
                "constraints": (
                    models.UniqueConstraint(
                        fields=("market", "subcategory"),
                        name="markets_market_subcategory_unique",
                    ),
                ),
            },
        ),
        migrations.AddField(
            model_name="market",
            name="subcategories",
            field=models.ManyToManyField(
                blank=True,
                related_name="markets",
                through="markets.MarketSubcategory",
                to="catalog.storesubcategory",
            ),
        ),
    ]
