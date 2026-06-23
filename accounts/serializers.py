import re

from django.contrib.auth import get_user_model
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .models import OneTimePassword
from .services import normalize_email, verify_otp

User = get_user_model()


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


class UserSerializer(RequiredFieldMessagesMixin, serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)
    has_password = serializers.SerializerMethodField()

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
        )

    def get_has_password(self, obj):
        return obj.has_usable_password()


class PasswordValidationMixin:
    def validate_password(self, value):
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
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    username = serializers.CharField(
        max_length=150,
        validators=[UnicodeUsernameValidator()],
    )
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=30)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)
    terms_accepted = serializers.BooleanField()

    def validate_email(self, value):
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
        email = normalize_email(self.initial_data.get("email", ""))
        user = User.objects.filter(
            username__iexact=username,
            deleted_at__isnull=True,
        ).first()
        if user and user.email.lower() != email:
            raise serializers.ValidationError("This username is already taken.")
        return username

    def validate_phone(self, value):
        phone = value.strip()
        user = User.objects.filter(
            phone=phone,
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
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        email = normalize_email(attrs["email"])
        user = User.objects.filter(
            email__iexact=email,
            deleted_at__isnull=True,
        ).first()

        if user is None or not user.check_password(attrs["password"]):
            raise AuthenticationFailed("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError(
                "Account email has not been verified."
            )

        attrs["user"] = user
        return attrs


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

        _, error = verify_otp(
            user,
            OneTimePassword.Purpose.PASSWORD_RESET,
            attrs["otp"],
        )
        if error:
            raise serializers.ValidationError({"otp": error})

        attrs["user"] = user
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
    last_name = serializers.CharField(max_length=150, required=False)
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
        user = self.context["request"].user
        if (
            User.objects.filter(username__iexact=username)
            .filter(deleted_at__isnull=True)
            .exclude(pk=user.pk)
            .exists()
        ):
            raise serializers.ValidationError("This username is already taken.")
        return username

    def validate_phone(self, value):
        phone = value.strip()
        user = self.context["request"].user
        if (
            User.objects.filter(phone=phone, deleted_at__isnull=True)
            .exclude(pk=user.pk)
            .exists()
        ):
            raise serializers.ValidationError(
                "An account with this phone number already exists."
            )
        return phone

    def update(self, instance, validated_data):
        update_fields = list(validated_data.keys())
        if (
            "username" in validated_data
            and validated_data["username"] != instance.username
        ):
            instance.username_changed_at = timezone.now()
            update_fields.append("username_changed_at")

        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save(update_fields=[*update_fields, "updated_at"])
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
