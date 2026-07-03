# Generated for market classification type filtering.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("markets", "0003_market_scope"),
    ]

    operations = [
        migrations.AddField(
            model_name="marketclassification",
            name="classification_type",
            field=models.CharField(
                choices=[
                    ("popular", "Popular"),
                    ("featured", "Featured"),
                    ("normal", "Normal"),
                ],
                default="normal",
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="marketclassification",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    classification_type__in=[
                        "popular",
                        "featured",
                        "normal",
                    ]
                ),
                name="markets_market_classification_type_valid",
            ),
        ),
    ]
