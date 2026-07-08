import re
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from locations.models import ServiceCity
from orders.models import Order

from .courier_rules import active_assigned_orders_for_user
from .models import CourierProfile, OneTimePassword
from .services import normalize_email, verify_otp

User = get_user_model()

AVATAR_MAX_SIZE = 5 * 1024 * 1024
AVATAR_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


def contains_whitespace(value):
    return bool(re.search(r"\s", value or ""))


def reject_whitespace(value):
    if contains_whitespace((value or "").strip()):
        raise serializers.ValidationError("Spaces are not allowed in this field.")
    return value


def no_whitespace_validator(value):
    reject_whitespace(value)


def phone_candidates(value):
    try:
        normalized = normalize_egyptian_phone(value)
    except serializers.ValidationError:
        return []

    if normalized.startswith("+213"):
        national = normalized[4:]
        candidates = {
            normalized,
            normalized[1:],
            national,
            f"0{national}",
        }
    else:
        national = normalized[3:]
        candidates = {
            normalized,
            normalized[1:],
            national,
            f"0{national}",
        }

    return list(candidates)


def normalize_egyptian_phone(value):
    phone = (value or "").strip()
    egypt_pattern = r"(?:01[0125]\d{8}|1[0125]\d{8}|201[0125]\d{8}|\+201[0125]\d{8})"
    algeria_pattern = r"(?:0[567]\d{8}|[567]\d{8}|213[567]\d{8}|\+213[567]\d{8})"
    pattern = rf"(?:{egypt_pattern}|{algeria_pattern})"
    if not re.fullmatch(pattern, phone):
        raise serializers.ValidationError(
            "Enter a valid mobile number."
        )

    if phone.startswith("+213"):
        return phone
    if phone.startswith("213"):
        return f"+{phone}"
    if re.fullmatch(r"0[567]\d{8}", phone):
        return f"+213{phone[1:]}"
    if re.fullmatch(r"[567]\d{8}", phone):
        return f"+213{phone}"
    if phone.startswith("+20"):
        return phone
    if phone.startswith("20"):
        return f"+{phone}"
    if phone.startswith("0"):
        return f"+20{phone[1:]}"
    return f"+20{phone}"


class RequiredFieldMessagesMixin:
    def get_fields(self):
        fields = super().get_fields()
        for name, field in fields.items():
            if field.required:
                label = field.label or name.replace("_", " ").capitalize()
                message = f"{label} is required."
                field.error_messages["required"] = message
                field.error_messages["blank"] = message
        return fields


class CourierProfileSerializer(RequiredFieldMessagesMixin, serializers.ModelSerializer):
    service_city_name = serializers.CharField(
        source="service_city.name",
        read_only=True,
    )
    service_city = serializers.PrimaryKeyRelatedField(
        queryset=ServiceCity.objects.filter(is_active=True),
        required=False,
    )

    class Meta:
        model = CourierProfile
        fields = (
            "vehicle_type",
            "plate_number",
            "delivery_area",
            "service_city",
            "service_city_name",
            "max_active_orders",
            "is_available",
        )
        extra_kwargs = {
            "delivery_area": {"required": False, "allow_null": True},
        }

    def validate_max_active_orders(self, value):
        if value < 1:
            raise serializers.ValidationError("Must be at least 1.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        service_city = attrs.get(
            "service_city",
            getattr(self.instance, "service_city", None),
        )
        if service_city is None:
            raise serializers.ValidationError(
                {"service_city": "Service city is required for couriers."}
            )
        if not service_city.is_active:
            raise serializers.ValidationError(
                {"service_city": "Service city must be active."}
            )
        attrs["delivery_area"] = None
        return attrs


class UserSerializer(RequiredFieldMessagesMixin, serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    avatar_url = serializers.SerializerMethodField()
    has_password = serializers.SerializerMethodField()
    courier_profile = CourierProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "first_name",
            "last_name",
            "username",
            "email",
            "phone",
            "gender",
            "birth_date",
            "avatar_url",
            "username_changed_at",
            "role",
            "has_password",
            "courier_profile",
        )

    def get_has_password(self, obj):
        return obj.has_usable_password()

    def get_avatar_url(self, obj):
        if obj.avatar_image:
            try:
                url = obj.avatar_image.url
            except ValueError:
                url = None
            if url:
                request = self.context.get("request")
                return request.build_absolute_uri(url) if request else url
        return obj.avatar_url or None


class AdminUserSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + (
            "is_active",
            "is_staff",
            "is_superuser",
            "last_login",
            "created_at",
            "updated_at",
        )


class AdminUserDetailSerializer(AdminUserSerializer):
    customer_stats = serializers.SerializerMethodField()
    recent_orders = serializers.SerializerMethodField()

    class Meta(AdminUserSerializer.Meta):
        fields = AdminUserSerializer.Meta.fields + (
            "customer_stats",
            "recent_orders",
        )

    def _order_number(self, order):
        return f"YM-{order.created_at:%Y%m%d}-{order.id:06d}"

    def get_customer_stats(self, obj):
        if obj.role != User.Role.CLIENT:
            return None

        completed_statuses = [Order.Status.DELIVERED]
        stats = obj.orders.aggregate(
            orders_count=Count("id"),
            completed_orders_count=Count(
                "id",
                filter=Q(status__in=completed_statuses),
            ),
            total_spent=Coalesce(
                Sum(
                    "total_price",
                    filter=Q(status__in=completed_statuses),
                ),
                0,
                output_field=Order._meta.get_field("total_price"),
            ),
            last_order_at=Max("created_at"),
        )

        return {
            "orders_count": stats["orders_count"],
            "completed_orders_count": stats["completed_orders_count"],
            "total_spent": f"{stats['total_spent']:.2f}",
            "last_order_at": stats["last_order_at"],
        }

    def get_recent_orders(self, obj):
        if obj.role != User.Role.CLIENT:
            return []

        orders = obj.orders.only(
            "id",
            "status",
            "total_price",
            "created_at",
        ).order_by("-created_at", "-id")[:10]

        return [
            {
                "id": order.id,
                "number": self._order_number(order),
                "status": order.status,
                "total": f"{order.total_price:.2f}",
                "created_at": order.created_at,
            }
            for order in orders
        ]


class PasswordValidationMixin:
    def validate_password(self, value):
        reject_whitespace(value)

        errors = []
        if len(value) < 8:
            errors.append("Password must be at least 8 characters.")
        if not re.search(r"[A-Z]", value):
            errors.append("Password must contain at least one uppercase letter.")
        if not re.search(r"\d", value):
            errors.append("Password must contain at least one number.")
        if not re.search(r"[^A-Za-z0-9]", value):
            errors.append("Password must contain at least one special character.")
        if errors:
            raise serializers.ValidationError(errors)

        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class RegisterSerializer(
    RequiredFieldMessagesMixin,
    PasswordValidationMixin,
    serializers.Serializer,
):
    first_name = serializers.CharField(
        max_length=150,
        validators=[no_whitespace_validator],
    )
    last_name = serializers.CharField(
        max_length=150,
        validators=[no_whitespace_validator],
    )
    username = serializers.CharField(
        max_length=150,
        validators=[no_whitespace_validator, UnicodeUsernameValidator()],
    )
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)
    terms_accepted = serializers.BooleanField()

   

    def validate_email(self, value):
        reject_whitespace(value)
        email = normalize_email(value)
        user = User.objects.filter(
            email__iexact=email,
            deleted_at__isnull=True,
        ).first()
        if user and user.is_active:
            raise serializers.ValidationError("An account with this email already exists.")
        return email

    def validate_username(self, value):
        username = value.strip()
        reject_whitespace(username)
        email = normalize_email(self.initial_data.get("email", ""))
        user = User.objects.filter(
            username__iexact=username,
            deleted_at__isnull=True,
        ).first()
        if user and user.email.lower() != email:
            raise serializers.ValidationError("This username is already taken.")
        return username

    def validate_phone(self, value):
        reject_whitespace(value)
        phone = normalize_egyptian_phone(value)
        user = User.objects.filter(
            phone__in=phone_candidates(phone),
            deleted_at__isnull=True,
        ).first()
        email = normalize_email(self.initial_data.get("email", ""))
        if user and user.email.lower() != email:
            raise serializers.ValidationError(
                "An account with this phone number already exists."
            )
        return phone

    def validate_terms_accepted(self, value):
        if not value:
            raise serializers.ValidationError(
                "You must accept the terms and conditions."
            )
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        return attrs


class EmailOTPSerializer(RequiredFieldMessagesMixin, serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.RegexField(r"^\d{6}$")

    def validate_email(self, value):
        return normalize_email(value)


class LoginSerializer(RequiredFieldMessagesMixin, serializers.Serializer):
    email = serializers.CharField(required=False)
    identifier = serializers.CharField(required=False, write_only=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        identifier = (attrs.get("identifier") or attrs.get("email") or "").strip()
        if not identifier:
            raise serializers.ValidationError(
                {"email": "Email, username, or phone number is required."}
            )

        user = self._find_user(identifier)

        if user is None or not user.check_password(attrs["password"]):
            raise AuthenticationFailed("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("Account is inactive.")
        expected_role = self.context.get("expected_role")
        if expected_role and user.role != expected_role:
            if expected_role == User.Role.REPRESENTATIVE:
                raise PermissionDenied(self._representative_wrong_role_error(user))
            role_label = User.Role(expected_role).label.lower()
            raise PermissionDenied(
                f"This login is only for {role_label} accounts."
            )

        attrs["user"] = user
        return attrs

    def _find_user(self, identifier):
        base_queryset = User.objects.filter(deleted_at__isnull=True)
        email = normalize_email(identifier)

        user = base_queryset.filter(email__iexact=email).first()
        if user is not None:
            return user

        user = base_queryset.filter(username__iexact=identifier).first()
        if user is not None:
            return user

        candidates = phone_candidates(identifier)
        if not candidates:
            return None

        return base_queryset.filter(phone__in=candidates).first()

    def _representative_wrong_role_error(self, user):
        if user.role == User.Role.ADMIN:
            return {
                "code": "admin_account_not_allowed",
                "detail": "This account belongs to an admin.",
            }
        if user.role == User.Role.CLIENT:
            return {
                "code": "client_account_not_allowed",
                "detail": "This account belongs to a client.",
            }
        return {
            "code": "representative_account_required",
            "detail": "This login is only for representative accounts.",
        }


class ForgotPasswordSerializer(RequiredFieldMessagesMixin, serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return normalize_email(value)


class ResetPasswordSerializer(PasswordValidationMixin, EmailOTPSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )

        user = User.objects.filter(
            email__iexact=attrs["email"],
            is_active=True,
            deleted_at__isnull=True,
        ).first()
        if user is None:
            raise serializers.ValidationError({"otp": "Invalid verification code."})

        otp_instance, error = verify_otp(
            user,
            OneTimePassword.Purpose.PASSWORD_RESET,
            attrs["otp"],
            consume=False,
        )
        if error:
            raise serializers.ValidationError({"otp": error})

        if user.check_password(attrs["password"]):
            raise serializers.ValidationError(
                {
                    "password": (
                        "New password must be different from your current password."
                    )
                }
            )

        attrs["user"] = user
        attrs["otp_instance"] = otp_instance
        return attrs


class LogoutSerializer(RequiredFieldMessagesMixin, serializers.Serializer):
    refresh = serializers.CharField(required=False)
    refreshToken = serializers.CharField(required=False, write_only=True)

    def validate(self, attrs):
        refresh = attrs.get("refresh") or attrs.get("refreshToken")
        if not refresh:
            raise serializers.ValidationError(
                {"refresh": "Refresh token is required."}
            )
        attrs["refresh"] = refresh
        return attrs

    def save(self, **kwargs):
        try:
            RefreshToken(self.validated_data["refresh"]).blacklist()
        except TokenError as exc:
            raise serializers.ValidationError(
                {"refresh": "Invalid or expired refresh token."}
            ) from exc


class UserUpdateSerializer(RequiredFieldMessagesMixin, serializers.Serializer):
    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
    )
    username = serializers.CharField(
        max_length=150,
        validators=[UnicodeUsernameValidator()],
        required=False,
    )
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(max_length=30, required=False)
    gender = serializers.CharField(max_length=20, required=False, allow_blank=True)
    birth_date = serializers.DateField(required=False, allow_null=True)
    avatar_url = serializers.URLField(required=False, allow_blank=True)
    avatar = serializers.ImageField(
        write_only=True,
        required=False,
        allow_null=False,
    )

    def validate_email(self, value):
        email = normalize_email(value)
        user = self.context["request"].user
        if (
            User.objects.filter(email__iexact=email)
            .filter(deleted_at__isnull=True)
            .exclude(pk=user.pk)
            .exists()
        ):
            raise serializers.ValidationError(
                "An account with this email already exists."
            )
        return email

    def validate_username(self, value):
        username = value.strip()
        reject_whitespace(username)
        user = self.context["request"].user
        if (
            User.objects.filter(username__iexact=username)
            .filter(deleted_at__isnull=True)
            .exclude(pk=user.pk)
            .exists()
        ):
            raise serializers.ValidationError("This username is already taken.")
        return username

    def validate_avatar(self, value):
        extension = Path(value.name or "").suffix.lower().lstrip(".")
        if extension not in AVATAR_ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                "Upload a valid profile photo: JPG, JPEG, PNG, or WEBP."
            )
        if value.size > AVATAR_MAX_SIZE:
            raise serializers.ValidationError(
                "Profile photo must be 5 MB or smaller."
            )
        return value

    def validate_phone(self, value):
        phone = normalize_egyptian_phone(value)
        user = self.context["request"].user
        if phone == user.phone:
            return phone
        if (
            User.objects.filter(
                phone__in=phone_candidates(phone),
                deleted_at__isnull=True,
            )
            .exclude(pk=user.pk)
            .exists()
        ):
            raise serializers.ValidationError(
                "An account with this phone number already exists."
            )
        return phone

    def validate(self, attrs):
        attrs = super().validate(attrs)
        username = attrs.get("username")
        if username is None:
            return attrs

        user = self.context["request"].user
        if username == user.username:
            return attrs

        if user.username_changed_at is not None:
            next_allowed_at = user.username_changed_at + timedelta(days=7)
            if timezone.now() < next_allowed_at:
                available_on = timezone.localtime(next_allowed_at).strftime("%Y-%m-%d")
                raise serializers.ValidationError(
                    {
                        "username": (
                            "Username can only be changed once every 7 days. "
                            f"You can change it again on {available_on}."
                        )
                    }
                )
        return attrs

    def update(self, instance, validated_data):
        avatar = validated_data.pop("avatar", None)
        old_avatar = instance.avatar_image if avatar is not None else None
        update_fields = []
        if (
            "username" in validated_data
            and validated_data["username"] != instance.username
        ):
            instance.username_changed_at = timezone.now()
            update_fields.append("username_changed_at")

        for field, value in validated_data.items():
            if getattr(instance, field) == value:
                continue
            setattr(instance, field, value)
            update_fields.append(field)
        if avatar is not None:
            instance.avatar_image = avatar
            update_fields.append("avatar_image")
        if update_fields:
            instance.save(update_fields=[*update_fields, "updated_at"])
        if (
            old_avatar
            and old_avatar.name
            and old_avatar.name != instance.avatar_image.name
        ):
            old_avatar.delete(save=False)
        return instance


class AdminUserWriteSerializer(
    RequiredFieldMessagesMixin,
    PasswordValidationMixin,
    serializers.ModelSerializer,
):
    password = serializers.CharField(
        required=False,
        write_only=True,
        trim_whitespace=False,
    )
    courier_profile = CourierProfileSerializer(required=False)
    avatar_image = serializers.ImageField(
        required=False,
        write_only=True,
        allow_null=False,
    )

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "username",
            "email",
            "phone",
            "password",
            "gender",
            "birth_date",
            "avatar_url",
            "avatar_image",
            "role",
            "is_active",
            "is_staff",
            "is_superuser",
            "courier_profile",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is None:
            self.fields["password"].required = True


    def validate_email(self, value):
        reject_whitespace(value)
        email = normalize_email(value)
        queryset = User.objects.filter(
            email__iexact=email,
            deleted_at__isnull=True,
        )
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "An account with this email already exists."
            )
        return email

    def validate_username(self, value):
        username = value.strip()
        reject_whitespace(username)
        queryset = User.objects.filter(
            username__iexact=username,
            deleted_at__isnull=True,
        )
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("This username is already taken.")
        return username

    def validate_phone(self, value):
        reject_whitespace(value)
        phone = normalize_egyptian_phone(value)
        queryset = User.objects.filter(
            phone__in=phone_candidates(phone),
            deleted_at__isnull=True,
        )
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "An account with this phone number already exists."
            )
        return phone

    def validate_avatar_image(self, value):
        extension = Path(value.name or "").suffix.lower().lstrip(".")
        if extension not in AVATAR_ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                "Upload a valid profile photo: JPG, JPEG, PNG, or WEBP."
            )
        if value.size > AVATAR_MAX_SIZE:
            raise serializers.ValidationError(
                "Profile photo must be 5 MB or smaller."
            )
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        role = attrs.get("role", getattr(self.instance, "role", None))
        profile_data = attrs.get("courier_profile")
        if profile_data is not None and role != User.Role.REPRESENTATIVE:
            raise serializers.ValidationError(
                {"courier_profile": "Courier profile is only valid for representatives."}
            )
        if (
            self.instance is not None
            and self.instance.role == User.Role.REPRESENTATIVE
            and attrs.get("is_active") is False
            and active_assigned_orders_for_user(self.instance).exists()
        ):
            raise serializers.ValidationError(
                {"is_active": "Reassign active orders before disabling this courier."}
            )
        password = attrs.get("password")
        if self.instance is not None and password and self.instance.check_password(password):
            raise serializers.ValidationError(
                {
                    "password": (
                        "كلمة المرور الجديدة يجب أن تكون مختلفة عن كلمة المرور الحالية."
                    )
                }
            )
        return attrs

    def create(self, validated_data):
        profile_data = validated_data.pop("courier_profile", None)
        avatar_image = validated_data.pop("avatar_image", None)
        password = validated_data.pop("password")
        user = User(**validated_data)
        if avatar_image is not None:
            user.avatar_image = avatar_image
        user.set_password(password)
        user.terms_accepted = True
        user.terms_accepted_at = timezone.now()
        user.save()
        if profile_data is not None:
            profile_data["delivery_area"] = None
            CourierProfile.objects.create(user=user, **profile_data)
        return user

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("courier_profile", None)
        avatar_image = validated_data.pop("avatar_image", None)
        password = validated_data.pop("password", None)
        update_fields = list(validated_data.keys())
        if (
            "username" in validated_data
            and validated_data["username"] != instance.username
        ):
            instance.username_changed_at = timezone.now()
            update_fields.append("username_changed_at")

        for field, value in validated_data.items():
            setattr(instance, field, value)
        old_avatar = instance.avatar_image if avatar_image is not None else None
        if avatar_image is not None:
            instance.avatar_image = avatar_image
            update_fields.append("avatar_image")
        if password is not None:
            instance.set_password(password)
            update_fields.append("password")
        if update_fields:
            instance.save(update_fields=[*update_fields, "updated_at"])
        if (
            old_avatar
            and old_avatar.name
            and old_avatar.name != instance.avatar_image.name
        ):
            old_avatar.delete(save=False)
        if instance.role != User.Role.REPRESENTATIVE:
            CourierProfile.objects.filter(user=instance).delete()
            return instance
        if profile_data is not None:
            profile_data["delivery_area"] = None
            profile, _ = CourierProfile.objects.get_or_create(
                user=instance,
                defaults=profile_data,
            )
            for field, value in profile_data.items():
                setattr(profile, field, value)
            profile.save()
        return instance


class DeleteAccountSerializer(RequiredFieldMessagesMixin, serializers.Serializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Invalid password.")
        return value


class EmailTokenRefreshSerializer(
    RequiredFieldMessagesMixin,
    TokenRefreshSerializer,
):
    refresh = serializers.CharField(required=False)
    refreshToken = serializers.CharField(required=False, write_only=True)

    def validate(self, attrs):
        refresh = attrs.get("refresh") or attrs.get("refreshToken")
        if not refresh:
            raise serializers.ValidationError(
                {"refresh": "Refresh token is required."}
            )
        data = super().validate({"refresh": refresh})
        return {
            "accessToken": data["access"],
            "refreshToken": data.get("refresh", refresh),
        }
