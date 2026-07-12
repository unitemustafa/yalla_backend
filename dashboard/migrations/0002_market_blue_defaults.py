from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dashboardsettings",
            name="primary_color",
            field=models.CharField(default="#4F60F6", max_length=7),
        ),
        migrations.AlterField(
            model_name="dashboardsettings",
            name="subtle_color",
            field=models.CharField(default="#EEF2FF", max_length=7),
        ),
        migrations.AlterField(
            model_name="dashboardsettings",
            name="accent_color",
            field=models.CharField(default="#14B8A6", max_length=7),
        ),
        migrations.AlterField(
            model_name="dashboardsettings",
            name="brand_name",
            field=models.CharField(default="يلا أدمن", max_length=120),
        ),
        migrations.AlterField(
            model_name="dashboardsettings",
            name="brand_tagline",
            field=models.CharField(
                default="أول أونلاين ماركت في التل الكبير", max_length=255
            ),
        ),
    ]
