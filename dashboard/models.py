from django.db import models
from config.media import raw_public_media_storage


class DashboardSettings(models.Model):
    primary_color = models.CharField(max_length=7, default="#4F60F6")
    subtle_color = models.CharField(max_length=7, default="#EEF2FF")
    accent_color = models.CharField(max_length=7, default="#14B8A6")
    font_family = models.CharField(max_length=30, default="Cairo")
    brand_name = models.CharField(max_length=120, default="يلا أدمن")
    brand_tagline = models.CharField(
        max_length=255,
        default="أول أونلاين ماركت في التل الكبير",
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


class AppLaunchMedia(models.Model):
    onboarding_one = models.ImageField(upload_to="app-launch/onboarding/", blank=True, null=True)
    onboarding_two = models.ImageField(upload_to="app-launch/onboarding/", blank=True, null=True)
    onboarding_three = models.ImageField(upload_to="app-launch/onboarding/", blank=True, null=True)
    market_login = models.ImageField(upload_to="app-launch/login/", blank=True, null=True)
    market_login_video = models.FileField(
        upload_to="app-launch/login/", storage=raw_public_media_storage, blank=True, null=True
    )
    delivery_login = models.ImageField(upload_to="app-launch/login/", blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "App launch media"
        verbose_name_plural = "App launch media"
