from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("offers", "0011_alter_homecampaign_options_and_more")]

    operations = [
        migrations.CreateModel(
            name="HomeCampaignImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to="home-campaigns/images/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="additional_images", to="offers.homecampaign")),
            ],
            options={"ordering": ("id",)},
        ),
    ]
