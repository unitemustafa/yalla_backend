# Generated manually for external announcement campaigns.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("offers", "0004_offer_multi_target_visibility"),
    ]

    operations = [
        migrations.AlterField(
            model_name="offer",
            name="market",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="offers",
                to="markets.market",
            ),
        ),
        migrations.AddField(
            model_name="offer",
            name="announcement_url",
            field=models.URLField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="offer",
            name="announcement_cta_label",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="offer",
            name="announcement_priority",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="offer",
            name="announcement_display_seconds",
            field=models.PositiveSmallIntegerField(default=15),
        ),
    ]
