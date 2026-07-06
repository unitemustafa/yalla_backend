from django.db import models


class DashboardSettings(models.Model):
    primary_color = models.CharField(max_length=7, default="#155d72")
    subtle_color = models.CharField(max_length=7, default="#e7f2f4")
    accent_color = models.CharField(max_length=7, default="#f0b64f")
    font_family = models.CharField(max_length=30, default="Cairo")
    brand_name = models.CharField(max_length=120, default="يلا ماركت")
    brand_tagline = models.CharField(
        max_length=255,
        default="أول أونلاين ماركت في النيل الكبير",
    )
    logo = models.ImageField(
        upload_to="dashboard/branding/",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Dashboard settings"
        verbose_name_plural = "Dashboard settings"

    def __str__(self):
        return self.brand_name
