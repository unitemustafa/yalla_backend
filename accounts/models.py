from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        CLIENT = "client", "Client"
        REPRESENTATIVE = "representative", "Representative"

    class MarketRegionMode(models.TextChoices):
        GENERAL = "general", "General"
        SERVICE_CITY = "service_city", "Service city"

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, unique=True)
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.CLIENT)
    gender = models.CharField(max_length=20, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    avatar_url = models.URLField(null=True, blank=True, db_column="avatar")
    avatar_image = models.ImageField(upload_to="avatars/", blank=True, null=True)
    username_changed_at = models.DateTimeField(null=True, blank=True)

    terms_accepted = models.BooleanField(default=False)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    privacy_policy_version = models.CharField(max_length=20, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deleted_original_email = models.EmailField(null=True, blank=True)
    deleted_original_username = models.CharField(max_length=150, null=True, blank=True)
    deleted_original_phone = models.CharField(max_length=30, null=True, blank=True)
    deleted_original_is_active = models.BooleanField(null=True, blank=True)
    market_region_mode = models.CharField(
        max_length=20,
        choices=MarketRegionMode.choices,
        null=True,
        blank=True,
    )
    market_region_service_city = models.ForeignKey(
        "locations.ServiceCity",
        on_delete=models.PROTECT,
        related_name="market_region_users",
        null=True,
        blank=True,
    )
    market_region_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("username"),
                name="accounts_user_username_ci_unique",
            ),
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(market_region_mode__isnull=True)
                        & models.Q(market_region_service_city__isnull=True)
                    )
                    | (
                        models.Q(market_region_mode="general")
                        & models.Q(market_region_service_city__isnull=True)
                    )
                    | (
                        models.Q(market_region_mode="service_city")
                        & models.Q(market_region_service_city__isnull=False)
                    )
                ),
                name="accounts_user_market_region_valid",
            ),
        ]


class CourierProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="courier_profile",
    )
    vehicle_type = models.CharField(max_length=100)
    plate_number = models.CharField(max_length=50)
    delivery_area = models.ForeignKey(
        "locations.DeliveryArea",
        on_delete=models.PROTECT,
        related_name="courier_profiles",
        blank=True,
        null=True,
    )
    service_city = models.ForeignKey(
        "locations.ServiceCity",
        on_delete=models.PROTECT,
        related_name="courier_profiles",
    )
    max_active_orders = models.PositiveSmallIntegerField(default=3)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class OneTimePassword(models.Model):
    class Purpose(models.TextChoices):
        REGISTRATION = "registration", "Registration"
        PASSWORD_RESET = "password_reset", "Password reset"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="one_time_passwords",
    )
    purpose = models.CharField(max_length=30, choices=Purpose.choices)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "purpose", "created_at"]),
        ]


class OTPCooldown(models.Model):
    purpose = models.CharField(max_length=30, choices=OneTimePassword.Purpose.choices)
    identifier = models.EmailField()
    resend_level = models.PositiveSmallIntegerField(default=0)
    next_allowed_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["purpose", "identifier"],
                name="accounts_otp_cooldown_purpose_identifier_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=["purpose", "identifier"],
                name="accounts_ot_purpose_757e7f_idx",
            ),
            models.Index(
                fields=["next_allowed_at"],
                name="accounts_ot_next_al_55e4ff_idx",
            ),
        ]
