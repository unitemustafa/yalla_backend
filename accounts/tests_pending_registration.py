from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from partners.models import PartnerApplication

from .models import OTPCooldown, PendingRegistration, User


AUTH_BASE = "/api/v1/auth"


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    AUTH_OTP_INCLUDE_IN_RESPONSE=True,
)
class PendingRegistrationAPITests(APITestCase):
    password = "StrongPassword123!"

    def payload(self):
        return {
            "first_name": "Pending",
            "last_name": "Customer",
            "username": "pending_customer",
            "email": "pending@example.com",
            "phone": "+213555000901",
            "password": self.password,
            "password_confirm": self.password,
            "terms_accepted": True,
        }

    def test_pending_identifiers_are_resumable_and_retry_reuses_one_row(self):
        first = self.client.post(f"{AUTH_BASE}/signup", self.payload())
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        checks = (
            self.client.get(
                f"{AUTH_BASE}/check-email", {"email": "pending@example.com"}
            ),
            self.client.get(
                f"{AUTH_BASE}/check-username", {"username": "pending_customer"}
            ),
            self.client.get(
                f"{AUTH_BASE}/check-phone", {"phone": "+213555000901"}
            ),
        )
        for response in checks:
            self.assertTrue(response.data["available"])
            self.assertFalse(response.data["registered"])
            self.assertTrue(response.data["verification_required"])

        cooldown = OTPCooldown.objects.get(identifier="pending@example.com")
        cooldown.next_allowed_at = timezone.now() - timedelta(seconds=1)
        cooldown.save(update_fields=["next_allowed_at"])
        retry = self.client.post(f"{AUTH_BASE}/signup", self.payload())

        self.assertEqual(retry.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PendingRegistration.objects.count(), 1)
        self.assertFalse(User.objects.filter(email="pending@example.com").exists())

    def test_pending_login_requires_correct_password_before_revealing_email(self):
        self.client.post(f"{AUTH_BASE}/signup", self.payload())

        wrong = self.client.post(
            f"{AUTH_BASE}/login/client/",
            {"identifier": "pending_customer", "password": "WrongPassword1!"},
        )
        correct = self.client.post(
            f"{AUTH_BASE}/login/client/",
            {"identifier": "pending_customer", "password": self.password},
        )

        self.assertEqual(wrong.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("email", wrong.data)
        self.assertEqual(correct.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(correct.data["code"], "email_verification_required")
        self.assertEqual(correct.data["email"], "pending@example.com")

    def test_verification_creates_exactly_one_real_user_and_consumes_pending(self):
        signup = self.client.post(f"{AUTH_BASE}/signup", self.payload())
        code = signup.data["dev_otp"]

        verified = self.client.post(
            f"{AUTH_BASE}/verify-email",
            {"email": "pending@example.com", "otp": code},
        )
        repeated = self.client.post(
            f"{AUTH_BASE}/verify-email",
            {"email": "pending@example.com", "otp": code},
        )

        self.assertEqual(verified.status_code, status.HTTP_200_OK)
        self.assertEqual(repeated.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.filter(email="pending@example.com").count(), 1)
        self.assertFalse(PendingRegistration.objects.exists())

    def test_admin_created_account_is_verified_and_discards_matching_pending(self):
        self.client.post(f"{AUTH_BASE}/signup", self.payload())
        admin = User.objects.create_superuser(
            username="pending_test_admin",
            email="pending-admin@example.com",
            phone="+213555000902",
            password=self.password,
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(admin).access_token}"
        )

        response = self.client.post(
            f"{AUTH_BASE}/users/",
            {
                "first_name": "Managed",
                "last_name": "Customer",
                "username": "pending_customer",
                "email": "pending@example.com",
                "phone": "+213555000901",
                "password": self.password,
                "role": User.Role.CLIENT,
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = User.objects.get(email="pending@example.com")
        self.assertTrue(created.is_verified)
        self.assertFalse(PendingRegistration.objects.exists())


class PendingRegistrationCleanupTests(APITestCase):
    def test_cleanup_uses_last_activity_and_never_deletes_users(self):
        now = timezone.now()
        stale = PendingRegistration.objects.create(
            first_name="Old",
            last_name="Pending",
            username="old_pending",
            email="old-pending@example.com",
            phone="+213555000911",
            password_hash="encoded",
            terms_accepted_at=now,
        )
        fresh = PendingRegistration.objects.create(
            first_name="Fresh",
            last_name="Pending",
            username="fresh_pending",
            email="fresh-pending@example.com",
            phone="+213555000912",
            password_hash="encoded",
            terms_accepted_at=now,
        )
        PendingRegistration.objects.filter(pk=stale.pk).update(
            updated_at=now - timedelta(hours=25)
        )
        deleted_user = User.objects.create_user(
            username="retained_deleted",
            email="retained-deleted@example.com",
            phone="+213555000913",
            password="StrongPassword123!",
            is_active=False,
            is_verified=False,
            deleted_at=now - timedelta(days=2),
        )
        PartnerApplication.objects.create(
            applicant=deleted_user,
            business_name="Retained",
            contact_first_name="Deleted",
            contact_last_name="User",
            business_type=PartnerApplication.BusinessType.SHOP,
            branches_count=1,
            applicant_role=PartnerApplication.ApplicantRole.OWNER_PARTNER,
            has_trade_license=True,
            email="retained-business@example.com",
            mobile_number="+213555000913",
        )

        output = StringIO()
        call_command("cleanup_unverified_users", stdout=output)

        self.assertFalse(PendingRegistration.objects.filter(pk=stale.pk).exists())
        self.assertTrue(PendingRegistration.objects.filter(pk=fresh.pk).exists())
        self.assertTrue(User.objects.filter(pk=deleted_user.pk).exists())
        self.assertIn("pending registrations=1", output.getvalue())
