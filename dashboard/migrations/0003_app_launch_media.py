from django.db import migrations, models
import config.media


class Migration(migrations.Migration):
    dependencies = [("dashboard", "0002_market_blue_defaults")]

    operations = [
        migrations.CreateModel(
            name="AppLaunchMedia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("onboarding_one", models.ImageField(blank=True, null=True, upload_to="app-launch/onboarding/")),
                ("onboarding_two", models.ImageField(blank=True, null=True, upload_to="app-launch/onboarding/")),
                ("onboarding_three", models.ImageField(blank=True, null=True, upload_to="app-launch/onboarding/")),
                ("market_login", models.ImageField(blank=True, null=True, upload_to="app-launch/login/")),
                ("market_login_video", models.FileField(blank=True, null=True, storage=config.media.raw_public_media_storage, upload_to="app-launch/login/")),
                ("delivery_login", models.ImageField(blank=True, null=True, upload_to="app-launch/login/")),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "App launch media", "verbose_name_plural": "App launch media"},
        ),
    ]
