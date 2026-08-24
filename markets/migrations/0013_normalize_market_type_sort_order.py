from django.db import migrations


def normalize_market_type_sort_order(apps, schema_editor):
    MarketType = apps.get_model("markets", "MarketType")
    classification_ids = MarketType.objects.values_list(
        "classification_id", flat=True
    ).distinct()

    for classification_id in classification_ids:
        market_types = list(
            MarketType.objects.filter(
                classification_id=classification_id
            ).order_by("sort_order", "id")
        )
        for sort_order, market_type in enumerate(market_types, start=1):
            market_type.sort_order = sort_order
        MarketType.objects.bulk_update(market_types, ["sort_order"])


class Migration(migrations.Migration):
    dependencies = [
        ("markets", "0012_market_types"),
    ]

    operations = [
        migrations.RunPython(
            normalize_market_type_sort_order,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
