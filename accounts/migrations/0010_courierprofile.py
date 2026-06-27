from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_alter_user_avatar_url"),
        ("locations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CourierProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("vehicle_type", models.CharField(max_length=100)),
                ("plate_number", models.CharField(max_length=50)),
                ("max_active_orders", models.PositiveSmallIntegerField(default=3)),
                ("is_available", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("delivery_area", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="courier_profiles", to="locations.deliveryarea")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="courier_profile", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
