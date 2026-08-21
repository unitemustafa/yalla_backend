from django.test import SimpleTestCase
from django.urls import reverse


class LegalPagesTests(SimpleTestCase):
    def test_public_legal_pages_render_on_mobile_friendly_html(self):
        expected_pages = {
            "privacy-policy": "Privacy Policy",
            "terms-of-use": "Terms of Use",
            "account-deletion": "Delete your account and data",
        }

        for route_name, heading in expected_pages.items():
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, heading)
                self.assertContains(response, 'name="viewport"')

    def test_deletion_page_exposes_a_remote_request_path(self):
        response = self.client.get(reverse("account-deletion"))

        self.assertContains(response, "Request deletion on WhatsApp")
        self.assertContains(response, "wa.me/201016487371")
