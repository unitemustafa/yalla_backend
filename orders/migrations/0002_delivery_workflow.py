from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_delivery_addresses(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    Address = apps.get_model("locations", "Address")
    for order in Order.objects.filter(delivery_address__isnull=True).iterator():
        address = (
            Address.objects.filter(user_id=order.user_id, is_default=True)
            .order_by("-created_at")
            .first()
            or Address.objects.filter(user_id=order.user_id)
            .order_by("-created_at")
            .first()
        )
        if address is not None:
            order.delivery_address_id = address.id
            order.save(update_fields=["delivery_address"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_courierprofile"),
        ("locations", "0001_initial"),
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.AddField(model_name="order", name="assigned_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="order", name="delivered_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="order", name="delivery_note", field=models.TextField(blank=True)),
        migrations.AddField(model_name="order", name="delivery_proof", field=models.ImageField(blank=True, null=True, upload_to="delivery-proofs/")),
        migrations.AddField(model_name="order", name="assigned_representative", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="assigned_orders", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="order", name="delivery_address", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="orders", to="locations.address")),
        migrations.RunPython(backfill_delivery_addresses, migrations.RunPython.noop),
    ]
