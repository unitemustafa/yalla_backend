from pathlib import Path

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from config.image_validation import validate_safe_image

from .courier_rules import active_assigned_orders_for_user
from .models import CourierProfile, OneTimePassword, PendingRegistration, User
from .services import clear_otp_cooldown, normalize_email
from .validation import (
    normalize_egyptian_phone,
    phone_candidates,
    reject_whitespace,
)

AVATAR_MAX_SIZE = 5 * 1024 * 1024
AVATAR_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


def _notify_courier_availability_change(courier_id, is_available):
    from notifications.services import create_courier_availability_notification

    courier = User.objects.filter(
        pk=courier_id,
        role=User.Role.REPRESENTATIVE,
    ).first()
    if courier is None:
        return

    create_courier_availability_notification(
        courier,
        is_available=is_available,
        source="admin",
    )


def _notify_courier_password_changed(courier_id):
    from notifications.services import create_courier_password_changed_notification

    courier = User.objects.filter(
        pk=courier_id,
        role=User.Role.REPRESENTATIVE,
    ).first()
    if courier is None:
        return

    create_courier_password_changed_notification(courier)


class AdminUserWriteMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is None:
            self.fields["password"].required = True
            return

        if self.instance.role == User.Role.REPRESENTATIVE:
            try:
                profile = self.instance.courier_profile
            except CourierProfile.DoesNotExist:
                profile = None
            if profile is not None:
                courier_profile_field = self.fields["courier_profile"]
                courier_profile_field.instance = profile
                courier_profile_field.partial = True

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
            raise serializers.ValidationError("Profile photo must be 5 MB or smaller.")
        return validate_safe_image(value)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        role = attrs.get("role", getattr(self.instance, "role", None))
        profile_data = attrs.get("courier_profile")
        if profile_data is not None and role != User.Role.REPRESENTATIVE:
            raise serializers.ValidationError(
                {
                    "courier_profile": "Courier profile is only valid for representatives."
                }
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
        if (
            self.instance is not None
            and self.instance.role in {User.Role.CLIENT, User.Role.REPRESENTATIVE}
            and self.instance.last_login is None
        ):
            current_availability = None
            if self.instance.role == User.Role.REPRESENTATIVE:
                try:
                    current_availability = self.instance.courier_profile.is_available
                except CourierProfile.DoesNotExist:
                    pass
            is_active_changed = (
                "is_active" in attrs and attrs["is_active"] != self.instance.is_active
            )
            is_available_changed = (
                self.instance.role == User.Role.REPRESENTATIVE
                and profile_data is not None
                and "is_available" in profile_data
                and profile_data["is_available"] != current_availability
            )
            if is_active_changed or is_available_changed:
                raise serializers.ValidationError(
                    {
                        "is_active": (
                            "The account must sign in once before its status can be changed."
                        )
                    }
                )
        password = attrs.get("password")
        if (
            self.instance is not None
            and password
            and self.instance.check_password(password)
        ):
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
        validated_data.pop("remove_avatar", None)
        password = validated_data.pop("password")
        user = User(**validated_data)
        if avatar_image is not None:
            user.avatar_image = avatar_image
        user.set_password(password)
        user.terms_accepted = True
        user.terms_accepted_at = timezone.now()
        user.is_verified = True
        user.save()
        pending_emails = list(
            PendingRegistration.objects.filter(
                Q(email__iexact=user.email)
                | Q(username__iexact=user.username)
                | Q(phone__in=phone_candidates(user.phone))
            ).values_list("email", flat=True)
        )
        PendingRegistration.objects.filter(email__in=pending_emails).delete()
        for email in pending_emails:
            clear_otp_cooldown(email, OneTimePassword.Purpose.REGISTRATION)
        if profile_data is not None:
            profile_data["delivery_area"] = None
            CourierProfile.objects.create(user=user, **profile_data)
        return user

    def update(self, instance, validated_data):
        was_active = instance.is_active
        was_role = instance.role
        profile_event_fields = {
            "first_name",
            "last_name",
            "phone",
            "avatar_image",
            "remove_avatar",
        }
        user_profile_changed = bool(profile_event_fields.intersection(validated_data))
        is_deactivation = was_active and validated_data.get("is_active") is False
        is_reactivation = not was_active and validated_data.get("is_active") is True
        profile_data = validated_data.pop("courier_profile", None)
        avatar_image = validated_data.pop("avatar_image", None)
        remove_avatar = validated_data.pop("remove_avatar", False)
        password = validated_data.pop("password", None)

        self._update_user_fields(
            instance,
            validated_data,
            avatar_image,
            remove_avatar,
            password,
        )
        self._sync_courier_profile(instance, profile_data)
        self._handle_account_status_change(
            instance,
            was_active,
            was_role,
            is_deactivation,
            is_reactivation,
        )
        self._schedule_courier_update_notifications(
            instance,
            profile_data,
            user_profile_changed,
            password_changed=password is not None,
        )
        return instance

    @staticmethod
    def _update_user_fields(
        instance,
        validated_data,
        avatar_image,
        remove_avatar,
        password,
    ):
        update_fields = list(validated_data.keys())
        if (
            "username" in validated_data
            and validated_data["username"] != instance.username
        ):
            instance.username_changed_at = timezone.now()
            update_fields.append("username_changed_at")

        for field, value in validated_data.items():
            setattr(instance, field, value)
        old_avatar = (
            instance.avatar_image if avatar_image is not None or remove_avatar else None
        )
        if avatar_image is not None:
            instance.avatar_image = avatar_image
            update_fields.append("avatar_image")
        elif remove_avatar:
            instance.avatar_image = None
            instance.avatar_url = None
            update_fields.extend(["avatar_image", "avatar_url"])
        if password is not None:
            instance.set_password(password)
            instance.auth_token_version += 1
            update_fields.extend(["password", "auth_token_version"])
        if update_fields:
            instance.save(update_fields=[*update_fields, "updated_at"])
        if (
            old_avatar
            and old_avatar.name
            and old_avatar.name != instance.avatar_image.name
        ):
            old_avatar.delete(save=False)

    @staticmethod
    def _sync_courier_profile(instance, profile_data):
        if instance.role != User.Role.REPRESENTATIVE:
            CourierProfile.objects.filter(user=instance).delete()
            return
        if profile_data is None:
            return

        profile_data["delivery_area"] = None
        profile, _ = CourierProfile.objects.get_or_create(
            user=instance,
            defaults=profile_data,
        )
        was_available = profile.is_available
        for field, value in profile_data.items():
            setattr(profile, field, value)
        profile.save()
        instance._state.fields_cache.pop("courier_profile", None)
        if "is_available" in profile_data and profile.is_available != was_available:
            transaction.on_commit(
                lambda courier_id=instance.id,
                is_available=profile.is_available: _notify_courier_availability_change(
                    courier_id,
                    is_available,
                )
            )

    @staticmethod
    def _handle_account_status_change(
        instance,
        was_active,
        was_role,
        is_deactivation,
        is_reactivation,
    ):
        if is_deactivation:
            from .deactivation import handle_client_deactivation

            handle_client_deactivation(
                instance,
                was_active=was_active,
                notify_disabled=False,
            )
        elif is_reactivation:
            if instance.role == instance.Role.CLIENT:
                from notifications.services import (
                    create_account_restored_notification,
                )

                create_account_restored_notification(instance)
            elif instance.role == instance.Role.REPRESENTATIVE:
                from notifications.services import (
                    create_courier_account_notification,
                )

                create_courier_account_notification(instance, restored=True)
        if is_deactivation and was_role == User.Role.REPRESENTATIVE:
            instance.auth_token_version += 1
            instance.save(update_fields=["auth_token_version", "updated_at"])
            from notifications.services import (
                create_courier_account_notification,
            )

            create_courier_account_notification(instance, restored=False)

    @staticmethod
    def _schedule_courier_update_notifications(
        instance,
        profile_data,
        user_profile_changed,
        *,
        password_changed,
    ):
        courier_profile_fields = {
            "vehicle_type",
            "plate_number",
            "service_city",
            "max_active_orders",
        }
        profile_changed = bool(courier_profile_fields.intersection(profile_data or {}))
        if instance.role == User.Role.REPRESENTATIVE and (
            user_profile_changed or profile_changed
        ):
            from notifications.services import (
                create_courier_profile_updated_notification,
            )

            create_courier_profile_updated_notification(instance)
        if password_changed and instance.role == instance.Role.REPRESENTATIVE:
            transaction.on_commit(
                lambda courier_id=instance.id: _notify_courier_password_changed(
                    courier_id,
                )
            )
