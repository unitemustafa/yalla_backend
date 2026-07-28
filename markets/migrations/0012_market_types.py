from django.db import migrations, models
import django.db.models.deletion
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [
        ("markets", "0011_market_storefront_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="MarketType",
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
                ("image", models.ImageField(upload_to="market-types/")),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "classification",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="market_types",
                        to="markets.marketclassification",
                    ),
                ),
            ],
            options={"ordering": ("sort_order", "id")},
        ),
        migrations.AddConstraint(
            model_name="markettype",
            constraint=models.UniqueConstraint(
                Lower("name_ar"),
                "classification",
                name="markets_market_type_name_ar_ci_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="markettype",
            constraint=models.UniqueConstraint(
                Lower("name_en"),
                "classification",
                name="markets_market_type_name_en_ci_unique",
            ),
        ),
        migrations.AddField(
            model_name="market",
            name="market_types",
            field=models.ManyToManyField(
                blank=True,
                related_name="markets",
                to="markets.markettype",
            ),
        ),
    ]
