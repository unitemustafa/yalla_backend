from django.db import migrations, models
import django.db.models.deletion


def copy_products_to_items(apps, schema_editor):
    Offer = apps.get_model("offers", "Offer")
    OfferItem = apps.get_model("offers", "OfferItem")

    pending = []
    for offer in Offer.objects.prefetch_related("products__variants").all():
        for product in offer.products.all():
            variant = product.variants.order_by("id").first()
            if variant is None:
                continue
            pending.append(
                OfferItem(
                    offer_id=offer.id,
                    variant_id=variant.id,
                    quantity=1,
                )
            )

    if pending:
        OfferItem.objects.bulk_create(pending, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0004_productimage"),
        ("offers", "0006_offer_push_notification_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="OfferItem",
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
                ("quantity", models.PositiveIntegerField(default=1)),
                (
                    "offer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="offers.offer",
                    ),
                ),
                (
                    "variant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="offer_items",
                        to="catalog.productvariant",
                    ),
                ),
            ],
            options={"ordering": ("id",)},
        ),
        migrations.AddConstraint(
            model_name="offeritem",
            constraint=models.UniqueConstraint(
                fields=("offer", "variant"),
                name="unique_offer_variant",
            ),
        ),
        migrations.RunPython(copy_products_to_items, migrations.RunPython.noop),
    ]
