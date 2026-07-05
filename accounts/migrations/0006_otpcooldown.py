from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_user_avatar_image"),
    ]

    operations = [
        migrations.CreateModel(
            name="OTPCooldown",
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
                (
                    "purpose",
                    models.CharField(
                        choices=[
                            ("registration", "Registration"),
                            ("password_reset", "Password reset"),
                        ],
                        max_length=30,
                    ),
                ),
                ("identifier", models.EmailField(max_length=254)),
                ("resend_level", models.PositiveSmallIntegerField(default=0)),
                ("next_allowed_at", models.DateTimeField(blank=True, null=True)),
                ("last_sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="otpcooldown",
            constraint=models.UniqueConstraint(
                fields=("purpose", "identifier"),
                name="accounts_otp_cooldown_purpose_identifier_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="otpcooldown",
            index=models.Index(
                fields=["purpose", "identifier"],
                name="accounts_ot_purpose_757e7f_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="otpcooldown",
            index=models.Index(
                fields=["next_allowed_at"],
                name="accounts_ot_next_al_55e4ff_idx",
            ),
        ),
    ]
