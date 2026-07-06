from django.db import migrations, models


def copy_offer_targets(apps, schema_editor):
    Offer = apps.get_model("offers", "Offer")
    through_model = Offer.service_cities.through

    rows = []
    for offer in Offer.objects.all().only("id", "scope", "service_city_id"):
        if offer.scope == "general":
            Offer.objects.filter(pk=offer.pk).update(show_in_general=True)
        elif offer.service_city_id:
            rows.append(
                through_model(
                    offer_id=offer.pk,
                    servicecity_id=offer.service_city_id,
                )
            )

    if rows:
        through_model.objects.bulk_create(rows, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ("locations", "0002_servicecity_delivery_price_address_service_city"),
        ("offers", "0003_offer_scope_offer_service_city_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="offer",
            name="show_in_general",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="offer",
            name="service_cities",
            field=models.ManyToManyField(
                blank=True,
                related_name="offers",
                to="locations.servicecity",
            ),
        ),
        migrations.RunPython(copy_offer_targets, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="offer",
            name="offers_offer_region_valid",
        ),
        migrations.RemoveField(
            model_name="offer",
            name="scope",
        ),
        migrations.RemoveField(
            model_name="offer",
            name="service_city",
        ),
    ]
