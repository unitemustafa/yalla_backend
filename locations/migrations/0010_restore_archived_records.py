from django.db import migrations


def restore_archived_records(apps, schema_editor):
    database = schema_editor.connection.alias
    records = (
        ("catalog", "Product", {"is_available": False}),
        ("markets", "Market", {"status": "inactive"}),
        ("offers", "Offer", {"status": "inactive"}),
        ("locations", "ServiceCity", {"is_active": False}),
        ("locations", "DeliveryArea", {"is_active": False}),
        ("locations", "ShippingCompany", {"is_active": False}),
    )
    for app_label, model_name, disabled_state in records:
        model = apps.get_model(app_label, model_name)
        model.objects.using(database).filter(archived_at__isnull=False).update(
            archived_at=None,
            **disabled_state,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0008_product_subcategories"),
        ("markets", "0013_normalize_market_type_sort_order"),
        ("offers", "0012_homecampaignimage"),
        ("locations", "0009_shippingcompany"),
    ]

    operations = [migrations.RunPython(restore_archived_records, migrations.RunPython.noop)]
