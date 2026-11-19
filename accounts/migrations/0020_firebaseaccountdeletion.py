from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0019_deferred_social_profile")]

    operations = [
        migrations.CreateModel(
            name="FirebaseAccountDeletion",
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
                ("firebase_uid", models.CharField(max_length=128, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
        ),
    ]
