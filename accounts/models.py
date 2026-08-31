from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.db.models.functions import Lower


class VerifiedUserManager(UserManager):
    """Programmatic provisioning is trusted unless it opts out explicitly."""

    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_verified", True)
        return super().create_user(
            username,
            email=email,
            password=password,
            **extra_fields,
        )

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_verified", True)
        # A Django superuser must also be an application admin. Force the
        # value so a caller cannot create an internally inconsistent account.
        extra_fields["role"] = User.Role.ADMIN
        return super().create_superuser(
            username,
            email=email,
            password=password,
            **extra_fields,
        )


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
    city = models.CharField(max_length=100, blank=True)
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
    auth_token_version = models.PositiveIntegerField(default=0)
    is_verified = models.BooleanField(default=False, db_index=True)
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

    objects = VerifiedUserManager()

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
            models.CheckConstraint(
                condition=(
                    models.Q(role="admin")
                    | (
                        models.Q(is_staff=False)
                        & models.Q(is_superuser=False)
                    )
                ),
                name="accounts_user_privileged_role_valid",
            ),
        ]


class PendingRegistration(models.Model):
    """A mobile signup that has not completed email verification yet."""

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    username = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, unique=True)
    city = models.CharField(max_length=100, blank=True)
    password_hash = models.CharField(max_length=128)
    firebase_uid = models.CharField(max_length=128, null=True, blank=True, unique=True)
    auth_provider = models.CharField(max_length=20, blank=True)
    avatar_url = models.URLField(null=True, blank=True)
    terms_accepted_at = models.DateTimeField()
    privacy_policy_version = models.CharField(max_length=20, blank=True)
    otp_code_hash = models.CharField(max_length=128, blank=True)
    otp_expires_at = models.DateTimeField(null=True, blank=True)
    otp_attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("username"),
                name="accounts_pending_username_ci_unique",
            ),
        ]


class SocialIdentity(models.Model):
    class Provider(models.TextChoices):
        GOOGLE = "google", "Google"
        FACEBOOK = "facebook", "Facebook"
        APPLE = "apple", "Apple"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="social_identities",
    )
    firebase_uid = models.CharField(max_length=128, unique=True)
    provider = models.CharField(max_length=20, choices=Provider.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "provider"],
                name="accounts_social_identity_user_provider_unique",
            )
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
