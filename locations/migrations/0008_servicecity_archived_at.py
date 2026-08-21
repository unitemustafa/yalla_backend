from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("locations", "0007_deliveryarea_archived_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicecity",
            name="archived_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
