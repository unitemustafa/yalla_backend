from rest_framework.test import APITestCase
from . import tests as notification_tests
from .models import Notification


class PagedNotificationTests(APITestCase):
    setUp = notification_tests.NotificationAPITests.setUp

    def test_unread_count_is_global_and_legacy_response_is_preserved(self):
        Notification.objects.bulk_create([
            Notification(audience=Notification.Audience.CLIENT, recipient=self.customer,
                type=Notification.Type.PASSWORD_CHANGED, title=f"Notice {i}", message="Test")
            for i in range(45)
        ])
        self.client.force_authenticate(self.customer)
        response = self.client.get("/api/v1/notifications/", {"page": 1, "page_size": 10})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertEqual(response.data["unread_count"], 45)
        self.assertEqual(response.data["count"], 45)
        legacy = self.client.get("/api/v1/notifications/")
        self.assertIsInstance(legacy.data, list)
        self.assertEqual(len(legacy.data), 45)
