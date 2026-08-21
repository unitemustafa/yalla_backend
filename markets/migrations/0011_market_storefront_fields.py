from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_clear_domain_data_preserve_users"),
        ("markets", "0010_market_archived_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="market",
            name="cover_image",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="markets/covers/",
            ),
        ),
        migrations.AddField(
            model_name="market",
            name="delivery_time_max_minutes",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="market",
            name="delivery_time_min_minutes",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="market",
            name="liked_by",
            field=models.ManyToManyField(
                blank=True,
                related_name="liked_markets",
                to="accounts.user",
            ),
        ),
        migrations.AddConstraint(
            model_name="market",
            constraint=models.CheckConstraint(
                condition=(
                    (
                        models.Q(delivery_time_min_minutes__isnull=True)
                        & models.Q(delivery_time_max_minutes__isnull=True)
                    )
                    | (
                        models.Q(delivery_time_min_minutes__gt=0)
                        & models.Q(delivery_time_max_minutes__gt=0)
                        & models.Q(
                            delivery_time_max_minutes__gte=models.F(
                                "delivery_time_min_minutes"
                            )
                        )
                    )
                ),
                name="markets_market_delivery_time_valid",
            ),
        ),
    ]
