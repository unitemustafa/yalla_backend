from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("offers", "0005_offer_announcement_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="offer",
            name="send_push_notification",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="offer",
            name="push_sent_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
