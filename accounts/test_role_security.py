from types import SimpleNamespace

from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import User
from .permissions import IsAdminRole, IsOrderAdminRole
from .serializers import AdminUserWriteSerializer


class PrivilegedRoleSecurityTests(TestCase):
    def test_create_superuser_always_uses_admin_role(self):
        user = User.objects.create_superuser(
            username="root_admin",
            email="root-admin@example.com",
            phone="+201000000001",
            password="StrongPassword123!",
            role=User.Role.CLIENT,
        )

        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_database_rejects_privileged_non_admin_user(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(
                username="invalid_staff_client",
                email="invalid-staff-client@example.com",
                phone="+201000000002",
                password="StrongPassword123!",
                role=User.Role.CLIENT,
                is_staff=True,
            )

    def test_admin_write_serializer_ignores_django_privilege_flags(self):
        serializer = AdminUserWriteSerializer(
            data={
                "first_name": "Safe",
                "last_name": "Client",
                "username": "safe_client",
                "email": "safe-client@example.com",
                "phone": "+201000000003",
                "password": "StrongPassword123!",
                "role": User.Role.CLIENT,
                "is_active": True,
                "is_staff": True,
                "is_superuser": True,
            }
        )

        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_staff_flag_never_grants_application_admin_access(self):
        user = SimpleNamespace(
            is_authenticated=True,
            role=User.Role.CLIENT,
            is_staff=True,
        )
        request = SimpleNamespace(user=user)

        self.assertFalse(IsAdminRole().has_permission(request, None))
        self.assertFalse(IsOrderAdminRole().has_permission(request, None))
