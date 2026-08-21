from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from accounts.models import User


class V2PaginationTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="pagination_admin",
            email="pagination-admin@example.com",
            phone="+201000000090",
            password="StrongPassword123!",
            role=User.Role.ADMIN,
        )
        User.objects.bulk_create(
            User(
                username=f"pagination_client_{index}",
                email=f"pagination-{index}@example.com",
                phone=f"+2011{index:08d}",
                role=User.Role.CLIENT,
            )
            for index in range(120)
        )
        self.client.force_authenticate(self.admin)

    def test_v1_list_contract_remains_an_array(self):
        response = self.client.get("/api/v1/auth/users/")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 121)

    def test_v2_list_is_paginated_with_default_size(self):
        response = self.client.get("/api/v2/auth/users/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 121)
        self.assertEqual(len(response.data["results"]), 50)
        self.assertIsNotNone(response.data["next"])
        self.assertIsNone(response.data["previous"])

    def test_v2_page_size_is_capped_at_one_hundred(self):
        response = self.client.get(
            "/api/v2/auth/users/",
            {"page_size": 999},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 100)

    def test_v2_user_page_has_a_bounded_query_count(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/v2/auth/users/")

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 4)
