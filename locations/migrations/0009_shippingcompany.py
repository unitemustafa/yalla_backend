from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [
        ("locations", "0008_servicecity_archived_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShippingCompany",
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
                ("name", models.CharField(max_length=150)),
                (
                    "logo",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to="shipping-companies/",
                    ),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                (
                    "archived_at",
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "service_cities",
                    models.ManyToManyField(
                        related_name="shipping_companies",
                        to="locations.servicecity",
                    ),
                ),
            ],
            options={"ordering": ("name", "id")},
        ),
        migrations.AddConstraint(
            model_name="shippingcompany",
            constraint=models.UniqueConstraint(
                Lower("name"),
                name="locations_shipping_company_name_ci_unique",
            ),
        ),
    ]
