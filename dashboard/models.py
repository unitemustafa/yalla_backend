from django.db import models
from config.media import raw_public_media_storage
from config.media import raw_private_media_storage, private_media_storage
from config.media_specs import top_focus
from django.conf import settings
import uuid


def delivery_apk_path(instance, filename):
    return f"app-updates/delivery/{instance.version_code}/{uuid.uuid4().hex}.apk"


class DeliveryAppRelease(models.Model):
    version_code = models.PositiveIntegerField(unique=True)
    version_name = models.CharField(max_length=40)
    release_notes = models.TextField(blank=True, max_length=4000)
    apk = models.FileField(upload_to=delivery_apk_path, storage=raw_public_media_storage)
    sha256 = models.CharField(max_length=64, editable=False)
    file_size = models.PositiveBigIntegerField(editable=False)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version_code"]
        constraints = [models.CheckConstraint(
            condition=models.Q(version_code__gte=1, version_code__lte=2_100_000_000),
            name="delivery_release_valid_version_code",
        )]


class MediaJob(models.Model):
    class State(models.TextChoices):
        PENDING = "pending"
        PROCESSING = "processing"
        READY = "ready"
        FAILED = "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    slot = models.CharField(max_length=24, choices=[("market_login", "Market login"), ("campaign", "Campaign")])
    state = models.CharField(max_length=12, choices=State.choices, default=State.PENDING, db_index=True)
    source = models.FileField(upload_to="media-jobs/sources/", storage=raw_private_media_storage, blank=True)
    video = models.FileField(upload_to="media-jobs/videos/", storage=raw_public_media_storage, blank=True)
    poster = models.ImageField(upload_to="media-jobs/posters/", blank=True)
    custom_poster = models.ImageField(upload_to="media-jobs/custom-posters/", storage=private_media_storage, blank=True)
    metadata = models.JSONField(default=dict)
    error = models.CharField(max_length=255, blank=True)
    error_code = models.CharField(max_length=32, blank=True)
    attempt = models.PositiveSmallIntegerField(default=0)
    attempt_token = models.UUIDField(null=True, editable=False)
    cancelled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ["-created_at"]


class MediaCleanup(models.Model):
    storage_id = models.CharField(max_length=20)
    name = models.CharField(max_length=500)
    delete_after = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["storage_id", "name"], name="unique_media_cleanup")]


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
    market_login_poster = models.ImageField(upload_to="app-launch/posters/", blank=True, null=True)
    market_login_focus = models.JSONField(default=top_focus)
    delivery_login_focus = models.JSONField(default=top_focus)
    market_login_pending_job = models.ForeignKey(MediaJob, null=True, blank=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "App launch media"
        verbose_name_plural = "App launch media"
