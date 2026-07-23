from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from notifications.models import Notification

from .models import PartnerApplication


class PartnerApplicationApiTests(APITestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(
            username="partner_client",
            email="partner-client@example.com",
            phone="01000000101",
            password="StrongPass!123",
            role=User.Role.CLIENT,
        )
        self.admin_user = User.objects.create_user(
            username="partner_admin",
            email="partner-admin@example.com",
            phone="01000000102",
            password="StrongPass!123",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.payload = {
            "business_name": "متجر الشروق",
            "contact_first_name": "أحمد",
            "contact_last_name": "علي",
            "business_type": PartnerApplication.BusinessType.SHOP,
            "branches_count": 2,
            "applicant_role": PartnerApplication.ApplicantRole.OWNER_PARTNER,
            "has_trade_license": True,
            "email": "owner@example.com",
            "mobile_number": "01012345678",
            "landline": "0223456789",
            "whatsapp_opt_in": True,
        }

    def create_application(self):
        self.client.force_authenticate(self.client_user)
        return self.client.post(
            "/api/v1/partners/applications/",
            self.payload,
            format="json",
        )

    def test_client_can_create_application_and_admin_notification(self):
        response = self.create_application()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        application = PartnerApplication.objects.get()
        self.assertEqual(application.applicant, self.client_user)
        notification = Notification.objects.get(
            type=Notification.Type.NEW_PARTNER_APPLICATION,
        )
        self.assertEqual(notification.audience, Notification.Audience.ADMIN)
        self.assertEqual(
            notification.data["partner_application_id"],
            application.id,
        )

    def test_open_application_cannot_be_submitted_twice(self):
        self.assertEqual(
            self.create_application().status_code,
            status.HTTP_201_CREATED,
        )

        response = self.client.post(
            "/api/v1/partners/applications/",
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(PartnerApplication.objects.count(), 1)

    def test_admin_can_list_and_approve_application(self):
        create_response = self.create_application()
        application_id = create_response.data["id"]
        self.client.force_authenticate(self.admin_user)

        list_response = self.client.get("/api/v1/partners/admin/applications/")
        update_response = self.client.patch(
            f"/api/v1/partners/admin/applications/{application_id}/",
            {"status": PartnerApplication.Status.APPROVED},
            format="json",
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_response.data), 1)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            update_response.data["status"],
            PartnerApplication.Status.APPROVED,
        )
        self.assertTrue(update_response.data["reviewed_at"])
        notification = Notification.objects.get(
            type=Notification.Type.NEW_PARTNER_APPLICATION,
        )
        self.assertTrue(notification.is_resolved)
        self.assertIsNotNone(notification.resolved_at)

    def test_non_admin_cannot_access_admin_list(self):
        self.create_application()

        response = self.client.get("/api/v1/partners/admin/applications/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_notification_is_visible_in_dashboard_feed(self):
        self.create_application()
        self.client.force_authenticate(self.admin_user)

        response = self.client.get("/api/v1/notifications/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data[0]["type"],
            Notification.Type.NEW_PARTNER_APPLICATION,
        )
        self.assertLessEqual(
            timezone.now() - PartnerApplication.objects.get().created_at,
            timedelta(seconds=5),
        )
