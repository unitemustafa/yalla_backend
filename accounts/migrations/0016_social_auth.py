from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounts", "0015_user_city_pendingregistration_city")]

    operations = [
        migrations.AddField(
            model_name="pendingregistration",
            name="auth_provider",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="pendingregistration",
            name="avatar_url",
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="pendingregistration",
            name="firebase_uid",
            field=models.CharField(
                blank=True,
                max_length=128,
                null=True,
                unique=True,
            ),
        ),
        migrations.CreateModel(
            name="SocialIdentity",
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
                (
                    "provider",
                    models.CharField(
                        choices=[
                            ("google", "Google"),
                            ("facebook", "Facebook"),
                            ("apple", "Apple"),
                        ],
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="social_identities",
                        to="accounts.user",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="socialidentity",
            constraint=models.UniqueConstraint(
                fields=("user", "provider"),
                name="accounts_social_identity_user_provider_unique",
            ),
        ),
    ]
