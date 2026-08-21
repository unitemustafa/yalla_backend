import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from locations.models import Address
from orders.models import Order
from partners.models import PartnerApplication

from .deactivation import revoke_user_sessions
from .models import OneTimePassword, User


ACTIVE_ORDER_STATUSES = (
    Order.Status.PENDING,
    Order.Status.CONFIRMED,
    Order.Status.ASSIGNED,
    Order.Status.PICKED_UP,
)


@transaction.atomic
def permanently_delete_client_account(user):
    """Anonymize a client while retaining non-personal transactional records."""
    user = User.objects.select_for_update().get(pk=user.pk)
    if user.role != User.Role.CLIENT or user.deleted_at is not None:
        raise ValidationError({"detail": "This account cannot be deleted."})

    if user.orders.filter(status__in=ACTIVE_ORDER_STATUSES).exists():
        raise ValidationError(
            {
                "detail": (
                    "Your account has an active order. Complete or cancel it "
                    "before deleting your account."
                )
            }
        )

    deletion_key = f"{user.pk}-{uuid.uuid4().hex[:12]}"
    old_avatar = user.avatar_image if user.avatar_image else None

    linked_address_ids = list(
        Address.objects.filter(user=user, orders__isnull=False)
        .values_list("id", flat=True)
        .distinct()
    )
    Address.objects.filter(user=user).exclude(id__in=linked_address_ids).delete()
    Address.objects.filter(id__in=linked_address_ids).update(
        name="Deleted address",
        details="",
        recipient_name="",
        recipient_phone="",
        street="",
        building_name="",
        apartment_number="",
        floor="",
        company_name="",
        additional_instructions="",
        label="",
        formatted_address="",
        place_id="",
        governorate="",
        district="",
        manual_city=None,
        manual_area=None,
        latitude=None,
        longitude=None,
    )

    user.notifications.all().delete()
    user.client_devices.all().delete()
    OneTimePassword.objects.filter(user=user).delete()
    user.liked_products.clear()
    PartnerApplication.objects.filter(applicant=user).update(
        business_name="[deleted]",
        contact_first_name="",
        contact_last_name="",
        email=f"deleted+{deletion_key}@deleted.invalid",
        mobile_number="",
        landline="",
        whatsapp_opt_in=False,
        notes="",
    )

    user.email = f"deleted+{deletion_key}@deleted.invalid"
    user.username = f"deleted_{deletion_key}"
    user.phone = f"deleted-{deletion_key}"[:30]
    user.first_name = ""
    user.last_name = ""
    user.gender = ""
    user.birth_date = None
    user.avatar_url = None
    user.avatar_image = None
    user.market_region_mode = None
    user.market_region_service_city = None
    user.market_region_updated_at = None
    user.terms_accepted = False
    user.terms_accepted_at = None
    user.privacy_policy_version = ""
    user.deleted_original_email = None
    user.deleted_original_username = None
    user.deleted_original_phone = None
    user.deleted_original_is_active = None
    user.deleted_at = timezone.now()
    user.is_active = False
    user.is_verified = False
    user.set_unusable_password()
    user.save()

    revoke_user_sessions(user)

    if old_avatar and old_avatar.name:
        transaction.on_commit(lambda: old_avatar.delete(save=False))

    return user
