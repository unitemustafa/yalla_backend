from django.core.management.color import no_style
from django.db import migrations


DELETE_ORDER = (
    ("notifications", "Notification"),
    ("notifications", "OfferNotificationDispatch"),
    ("notifications", "ProductNotificationDispatch"),
    ("notifications", "DeliveryAreaNotificationDispatch"),
    ("notifications", "MarketNotificationDispatch"),
    ("notifications", "ClientDevice"),
    ("orders", "OrderEvent"),
    ("orders", "OrderItem"),
    ("orders", "OrderOffer"),
    ("orders", "OrderMarketSection"),
    ("orders", "Order"),
    ("offers", "OfferItem"),
    ("offers", "Offer"),
    ("catalog", "VariantAttributeValue"),
    ("catalog", "ProductAttributeValue"),
    ("catalog", "ProductImage"),
    ("catalog", "ProductAttributeOption"),
    ("catalog", "ProductAttribute"),
    ("catalog", "ProductVariant"),
    ("catalog", "Product"),
    ("catalog", "ProductAddition"),
    ("catalog", "AdditionClassification"),
    ("catalog", "CategoryOption"),
    ("catalog", "CategoryAttribute"),
    ("catalog", "ProductCategory"),
    ("markets", "MarketSubcategory"),
    ("catalog", "StoreSubcategory"),
    ("catalog", "CategoryClassification"),
    ("markets", "Market"),
    ("markets", "MarketClassification"),
    ("locations", "Address"),
    ("accounts", "CourierProfile"),
    ("accounts", "OneTimePassword"),
    ("accounts", "OTPCooldown"),
    ("dashboard", "DashboardSettings"),
    ("locations", "DeliveryArea"),
    ("locations", "ServiceCity"),
)


def clear_domain_data_preserve_users(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    preserved_users = User.objects.count()
    User.objects.update(
        market_region_mode=None,
        market_region_service_city=None,
        market_region_updated_at=None,
    )

    deleted_models = []
    for app_label, model_name in DELETE_ORDER:
        model = apps.get_model(app_label, model_name)
        model.objects.all().delete()
        deleted_models.append(model)

    statements = schema_editor.connection.ops.sequence_reset_sql(
        no_style(),
        deleted_models,
    )
    if statements:
        with schema_editor.connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)

    print(
        "Production domain reset complete: "
        f"preserved {preserved_users} user account(s)."
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_alter_user_managers"),
        ("catalog", "0007_product_archived_at"),
        ("dashboard", "0002_market_blue_defaults"),
        ("locations", "0008_servicecity_archived_at"),
        ("markets", "0010_market_archived_at"),
        ("notifications", "0012_partner_application_approved"),
        ("offers", "0009_offer_archived_at"),
        (
            "orders",
            "0010_remove_order_orders_order_scope_service_city_valid_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(
            clear_domain_data_preserve_users,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
