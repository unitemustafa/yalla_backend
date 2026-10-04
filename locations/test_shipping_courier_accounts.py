from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import CourierProfile, User
from accounts.serializers import CourierProfileSerializer, UserSerializer
from markets.models import Market, MarketClassification
from orders.models import Order
from orders.selectors import eligible_representatives_for_order

from .models import ServiceCity, ShippingCompany
from .tests import shipping_logo_upload


class ShippingCourierAccountTests(TestCase):
    base = "/api/v1/locations/shipping-companies/"

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="shipping-owner",
            email="owner@example.com",
            role=User.Role.ADMIN,
        )
        self.customer = User.objects.create_user(
            username="shipping-customer",
            email="customer@example.com",
        )
        self.client.force_authenticate(self.admin)
        self.city = ServiceCity.objects.create(name="Cairo")
        self.other_city = ServiceCity.objects.create(name="Giza")
        classification = MarketClassification.objects.create(name="Shipping market")
        self.market = Market.objects.create(
            name="Market", classification=classification
        )

    def create_company(self, *, request_format="json", **extra):
        response = self.client.post(
            self.base,
            {
                "name": "Global Shipping",
                "email": " Company@Example.com ",
                "password": "CompanyPass1!",
                **extra,
            },
            format=request_format,
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["email"], "company@example.com")
        self.assertNotIn("password", response.data)
        return ShippingCompany.objects.get(pk=response.data["id"])

    def order(self, city=None):
        return Order.objects.create(
            user=self.customer,
            market=self.market,
            payment_method="cash",
            service_city=city,
            order_scope=Order.Scope.SERVICE_CITY if city else Order.Scope.GENERAL,
            status=Order.Status.CONFIRMED,
            review_status=Order.ReviewStatus.APPROVED,
        )

    def test_create_company_provisions_verified_courier_and_fixed_profile(self):
        company = self.create_company()
        user = company.courier_account
        self.assertEqual(user.role, User.Role.REPRESENTATIVE)
        self.assertTrue(user.is_verified)
        self.assertTrue(user.check_password("CompanyPass1!"))
        profile = CourierProfileSerializer(user.courier_profile).data
        self.assertEqual(profile["service_city_name"], "كل المدن")
        self.assertIsNone(profile["service_city"])
        self.assertIsNone(profile["max_active_orders"])
        self.assertTrue(profile["is_shipping_company"])
        self.assertEqual(profile["vehicle_type"], "شركة شحن")
        self.assertEqual(profile["plate_number"], "شركة شحن")

    def test_create_global_company_from_multipart_without_cities(self):
        company = self.create_company(request_format="multipart")
        self.assertFalse(company.service_cities.exists())
        self.assertIsNone(company.courier_account.courier_profile.service_city_id)

    def test_create_global_company_with_logo_and_without_cities(self):
        company = self.create_company(
            request_format="multipart", logo=shipping_logo_upload()
        )
        self.assertFalse(company.service_cities.exists())
        self.assertTrue(company.logo.storage.exists(company.logo.name))
        self.assertIsNotNone(company.courier_account_id)

    def test_courier_login_and_profile_use_existing_company_logo(self):
        company = self.create_company(
            request_format="multipart", logo=shipping_logo_upload(), is_active=True
        )
        expected_url = f"http://testserver{company.logo.url}"
        self.client.force_authenticate(user=None)
        login = self.client.post(
            "/api/v1/auth/login/representative/",
            {"email": "company@example.com", "password": "CompanyPass1!"},
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.data)
        self.assertEqual(login.data["user"]["avatar_url"], expected_url)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {login.data['accessToken']}"
        )
        profile = self.client.get("/api/v1/auth/me/")
        self.assertEqual(profile.status_code, 200, profile.data)
        self.assertEqual(profile.data["avatar_url"], expected_url)

    def test_company_logo_replacement_and_removal_update_courier_profile(self):
        company = self.create_company(
            request_format="multipart", logo=shipping_logo_upload()
        )
        old_url = company.logo.url
        replaced = self.client.patch(
            f"{self.base}{company.pk}/",
            {"logo": shipping_logo_upload("updated-shipping-logo.png")},
            format="multipart",
        )
        self.assertEqual(replaced.status_code, 200, replaced.data)
        company.refresh_from_db()
        self.assertNotEqual(company.logo.url, old_url)
        self.client.force_authenticate(User.objects.get(pk=company.courier_account_id))
        profile = self.client.get("/api/v1/auth/me/")
        self.assertEqual(
            profile.data["avatar_url"], f"http://testserver{company.logo.url}"
        )

        self.client.force_authenticate(self.admin)
        removed = self.client.patch(
            f"{self.base}{company.pk}/", {"remove_logo": True}, format="json"
        )
        self.assertEqual(removed.status_code, 200, removed.data)
        self.client.force_authenticate(User.objects.get(pk=company.courier_account_id))
        profile = self.client.get("/api/v1/auth/me/")
        self.assertIsNone(profile.data["avatar_url"])

    def test_company_logo_takes_priority_over_separate_user_avatar(self):
        company = self.create_company(
            request_format="multipart", logo=shipping_logo_upload()
        )
        user = company.courier_account
        user.avatar_image = "avatars/separate-courier.png"
        user.avatar_url = "https://example.com/old-avatar.png"
        user.save(update_fields=["avatar_image", "avatar_url"])
        self.assertEqual(UserSerializer(user).data["avatar_url"], company.logo.url)

    def test_regular_account_avatar_is_preserved(self):
        self.customer.avatar_url = "https://example.com/customer-avatar.png"
        self.assertEqual(
            UserSerializer(self.customer).data["avatar_url"], self.customer.avatar_url
        )
        self.customer.avatar_image = "avatars/customer.png"
        self.assertEqual(
            UserSerializer(self.customer).data["avatar_url"],
            self.customer.avatar_image.url,
        )

    def test_create_global_company_accepts_explicit_empty_cities(self):
        company = self.create_company(service_city_ids=[])
        self.assertFalse(company.service_cities.exists())
        self.assertIsNotNone(company.courier_account_id)

    def test_update_global_company_with_logo_and_without_cities(self):
        company = self.create_company()
        response = self.client.patch(
            f"{self.base}{company.pk}/",
            {"name": "Updated Shipping", "logo": shipping_logo_upload()},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.data)
        company.refresh_from_db()
        self.assertEqual(company.name, "Updated Shipping")
        self.assertTrue(company.logo.storage.exists(company.logo.name))
        self.assertFalse(company.service_cities.exists())
        self.assertIsNone(company.courier_account.courier_profile.service_city_id)

    def test_company_can_login_in_courier_app_and_read_assigned_order(self):
        company = self.create_company()
        order = self.order(self.other_city)
        assignment = self.client.patch(
            f"/api/v1/orders/{order.pk}/assignment/",
            {
                "representative_id": company.courier_account_id,
            },
            format="json",
        )
        self.assertEqual(assignment.status_code, 200, assignment.data)
        self.client.force_authenticate(user=None)
        login = self.client.post(
            "/api/v1/auth/login/representative/",
            {
                "email": "company@example.com",
                "password": "CompanyPass1!",
            },
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.data)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {login.data['accessToken']}"
        )
        detail = self.client.get(f"/api/v1/courier/orders/{order.pk}/")
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(detail.data["id"], order.pk)

    def test_company_is_eligible_in_every_city_and_general_orders(self):
        company = self.create_company()
        regular_couriers = {}
        for city in (self.city, self.other_city):
            courier = User.objects.create_user(
                username=f"regular-courier-{city.pk}",
                email=f"regular-courier-{city.pk}@example.com",
                role=User.Role.REPRESENTATIVE,
            )
            CourierProfile.objects.create(
                user=courier,
                vehicle_type="Bike",
                plate_number=f"plate-{city.pk}",
                service_city=city,
            )
            regular_couriers[city.pk] = courier.pk
        for city in (self.city, self.other_city, None):
            order = self.order(city)
            expected_ids = {company.courier_account_id}
            expected_ids.update(
                [regular_couriers[city.pk]] if city else regular_couriers.values()
            )
            self.assertEqual(
                set(
                    eligible_representatives_for_order(order).values_list(
                        "id", flat=True
                    )
                ),
                expected_ids,
            )
            options = self.client.get(
                f"/api/v1/admin/orders/{order.pk}/service-city-representatives/"
            )
            self.assertEqual(options.status_code, 200, options.data)
            self.assertEqual(
                {row["representative_id"] for row in options.data["representatives"]},
                expected_ids,
            )
            assignment = self.client.patch(
                f"/api/v1/orders/{order.pk}/assignment/",
                {
                    "representative_id": company.courier_account_id,
                },
                format="json",
            )
            self.assertEqual(assignment.status_code, 200, assignment.data)
        self.assertEqual(company.courier_account.assigned_orders.count(), 3)

    def test_client_company_list_includes_global_company_without_credentials(self):
        company = self.create_company()
        self.client.force_authenticate(self.customer)
        response = self.client.get(f"{self.base}?service_city_id={self.other_city.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data], [company.pk])
        for row in response.data:
            self.assertNotIn("email", row)
            self.assertNotIn("password", row)
            self.assertNotIn("courier_account_id", row)

    def test_creation_validates_credentials_and_does_not_leave_partial_company(self):
        for overrides in (
            {},
            {"email": "owner@example.com", "password": "CompanyPass1!"},
            {"email": "new@example.com", "password": "short"},
        ):
            response = self.client.post(
                self.base, {"name": "Invalid Company", **overrides}, format="json"
            )
            self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(
            ShippingCompany.objects.filter(name="Invalid Company").exists()
        )

    def test_company_password_update_invalidates_old_credentials(self):
        company = self.create_company()
        response = self.client.patch(
            f"{self.base}{company.pk}/",
            {
                "password": "UpdatedPass2!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        user = User.objects.get(pk=company.courier_account_id)
        self.assertFalse(user.check_password("CompanyPass1!"))
        self.assertTrue(user.check_password("UpdatedPass2!"))
        self.assertEqual(user.auth_token_version, 1)

    def test_legacy_metadata_update_works_and_credentials_can_provision_account(self):
        company = ShippingCompany.objects.create(name="Legacy Shipping")
        response = self.client.patch(
            f"{self.base}{company.pk}/", {"is_active": False}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        company.refresh_from_db()
        self.assertIsNone(company.courier_account_id)
        response = self.client.patch(
            f"{self.base}{company.pk}/",
            {
                "email": "legacy@example.com",
                "password": "LegacyPass1!",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        company.refresh_from_db()
        self.assertIsNotNone(company.courier_account_id)

    def test_company_profile_edits_cannot_change_fixed_fields_or_role(self):
        company = self.create_company()
        response = self.client.patch(
            f"/api/v1/auth/users/{company.courier_account_id}/",
            {
                "courier_profile": {
                    "service_city": self.city.pk,
                    "max_active_orders": 1,
                    "vehicle_type": "Bike",
                    "plate_number": "123",
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        profile = CourierProfile.objects.get(user_id=company.courier_account_id)
        self.assertIsNone(profile.service_city_id)
        self.assertIsNone(profile.max_active_orders)
        self.assertEqual(profile.vehicle_type, "شركة شحن")
        self.assertEqual(profile.plate_number, "شركة شحن")
        response = self.client.patch(
            f"/api/v1/auth/users/{company.courier_account_id}/",
            {"role": "client"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)

    def test_company_disable_syncs_user_and_excludes_assignment(self):
        company = self.create_company()
        response = self.client.patch(
            f"{self.base}{company.pk}/", {"is_active": False}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        user = User.objects.get(pk=company.courier_account_id)
        self.assertFalse(user.is_active)
        self.assertEqual(user.auth_token_version, 1)
        self.assertNotIn(
            user.pk,
            eligible_representatives_for_order(self.order(self.city)).values_list(
                "id", flat=True
            ),
        )

    def test_user_status_updates_sync_company_status(self):
        company = self.create_company()
        user = company.courier_account
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        response = self.client.patch(
            f"/api/v1/auth/users/{user.pk}/", {"is_active": False}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        company.refresh_from_db()
        self.assertFalse(company.is_active)

    def test_delete_unused_company_revokes_account_and_removes_profile(self):
        company = self.create_company()
        user_id = company.courier_account_id
        response = self.client.delete(f"{self.base}{company.pk}/")
        self.assertEqual(response.status_code, 204, response.data)
        user = User.objects.get(pk=user_id)
        self.assertFalse(user.is_active)
        self.assertEqual(user.auth_token_version, 1)
        self.assertFalse(CourierProfile.objects.filter(user=user).exists())

    def test_active_assignments_block_disable_and_assignment_history_blocks_delete(
        self,
    ):
        company = self.create_company()
        order = self.order(self.city)
        order.assigned_representative = company.courier_account
        order.status = Order.Status.ASSIGNED
        order.save()
        disabled = self.client.patch(
            f"{self.base}{company.pk}/", {"is_active": False}, format="json"
        )
        self.assertEqual(disabled.status_code, 400, disabled.data)
        order.status = Order.Status.DELIVERED
        order.save()
        deleted = self.client.delete(f"{self.base}{company.pk}/")
        self.assertEqual(deleted.status_code, 409, deleted.data)


class OptionalCourierCapacityTests(TestCase):
    def setUp(self):
        self.city = ServiceCity.objects.create(name="Courier City")
        self.data = {
            "vehicle_type": "Bike",
            "plate_number": "123",
            "service_city": self.city.pk,
        }

    def test_omitted_and_null_capacity_are_unlimited(self):
        for extra in ({}, {"max_active_orders": None}):
            serializer = CourierProfileSerializer(data={**self.data, **extra})
            self.assertTrue(serializer.is_valid(), serializer.errors)
            user = User.objects.create_user(
                username=f"courier-{len(extra)}",
                email=f"courier-{len(extra)}@example.com",
                role=User.Role.REPRESENTATIVE,
            )
            profile = serializer.save(user=user)
            self.assertIsNone(profile.max_active_orders)

    def test_finite_capacity_must_be_positive_integer(self):
        for value in (0, -1, "1.5"):
            serializer = CourierProfileSerializer(
                data={**self.data, "max_active_orders": value}
            )
            self.assertFalse(serializer.is_valid())
            self.assertIn("max_active_orders", serializer.errors)
        serializer = CourierProfileSerializer(
            data={**self.data, "max_active_orders": 2}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_regular_courier_still_requires_city(self):
        serializer = CourierProfileSerializer(data={**self.data, "service_city": None})
        self.assertFalse(serializer.is_valid())
        self.assertIn("service_city", serializer.errors)
