import django.db.models.deletion
from django.db import migrations, models


OTHER_NAME_AR = "أخرى"
OTHER_NAME_EN = "Other"


def _clean(value):
    return (value or "").strip()


def _normalized(value):
    return _clean(value).casefold()


def backfill_store_subcategories(apps, schema_editor):
    Market = apps.get_model("markets", "Market")
    MarketSubcategory = apps.get_model("markets", "MarketSubcategory")
    Product = apps.get_model("catalog", "Product")
    ProductCategory = apps.get_model("catalog", "ProductCategory")
    StoreSubcategory = apps.get_model("catalog", "StoreSubcategory")

    by_name = {}
    for category in ProductCategory.objects.order_by("id").iterator():
        name = _clean(category.name)
        if not name:
            continue
        key = _normalized(name)
        subcategory = by_name.get(key)
        if subcategory is None:
            subcategory = StoreSubcategory.objects.create(
                name_ar=name,
                name_en=name,
                description_ar=_clean(category.description),
                description_en=_clean(category.description),
                image=category.image,
                is_active=True,
            )
            by_name[key] = subcategory
        else:
            update_fields = []
            if not subcategory.description_ar and category.description:
                subcategory.description_ar = category.description
                subcategory.description_en = category.description
                update_fields.extend(("description_ar", "description_en"))
            if not subcategory.image and category.image:
                subcategory.image = category.image
                update_fields.append("image")
            if update_fields:
                subcategory.save(update_fields=update_fields)

        Product.objects.filter(
            category_id=category.id,
            subcategory__isnull=True,
        ).update(subcategory_id=subcategory.id)

    other_ar = StoreSubcategory.objects.filter(
        name_ar__iexact=OTHER_NAME_AR
    ).first()
    other_en = StoreSubcategory.objects.filter(
        name_en__iexact=OTHER_NAME_EN
    ).first()
    if other_ar is not None and other_en is not None and other_ar.id != other_en.id:
        Product.objects.filter(subcategory_id=other_en.id).update(
            subcategory_id=other_ar.id
        )
        other_en.delete()
    other = other_ar or other_en
    if other is None:
        other = StoreSubcategory.objects.create(
            name_ar=OTHER_NAME_AR,
            name_en=OTHER_NAME_EN,
            description_ar="",
            description_en="",
            is_active=True,
        )
    else:
        other.name_ar = OTHER_NAME_AR
        other.name_en = OTHER_NAME_EN
        other.is_active = True
        other.save(update_fields=("name_ar", "name_en", "is_active"))
    Product.objects.filter(subcategory__isnull=True).update(
        subcategory_id=other.id
    )

    for market in Market.objects.order_by("id").iterator():
        subcategory_ids = list(
            Product.objects.filter(market_id=market.id)
            .order_by("subcategory_id")
            .values_list("subcategory_id", flat=True)
            .distinct()
        )
        if not subcategory_ids:
            subcategory_ids = [other.id]
        MarketSubcategory.objects.bulk_create(
            [
                MarketSubcategory(
                    market_id=market.id,
                    subcategory_id=subcategory_id,
                    sort_order=index,
                )
                for index, subcategory_id in enumerate(subcategory_ids)
            ],
            ignore_conflicts=True,
        )


def reverse_backfill(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    Product.objects.update(subcategory=None)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0005_store_subcategories"),
        ("markets", "0009_market_subcategories"),
    ]

    operations = [
        migrations.RunPython(
            backfill_store_subcategories,
            reverse_backfill,
        ),
        migrations.AlterField(
            model_name="product",
            name="subcategory",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="products",
                to="catalog.storesubcategory",
            ),
        ),
    ]
