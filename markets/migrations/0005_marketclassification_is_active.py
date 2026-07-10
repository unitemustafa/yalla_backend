from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("markets", "0004_marketclassification_classification_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="marketclassification",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]
