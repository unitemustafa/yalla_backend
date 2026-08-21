from types import SimpleNamespace

from django.test import SimpleTestCase
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.permissions import AllowAny, IsAuthenticated

from accounts.models import User
from accounts.permissions import HasRole


PUBLIC_API_ROUTE_NAMES = {
    "signup",
    "signup-slash",
    "verify-email",
    "verify-email-slash",
    "resend-verification",
    "resend-verification-slash",
    "login",
    "login-slash",
    "client-login",
    "client-login-slash",
    "representative-login",
    "representative-login-slash",
    "admin-login",
    "admin-login-slash",
    "token-refresh",
    "token-refresh-slash",
    "check-username",
    "check-username-slash",
    "check-email",
    "check-email-slash",
    "check-phone",
    "check-phone-slash",
    "forgot-password",
    "forgot-password-slash",
    "reset-password",
    "reset-password-slash",
    "login-dashboard-snapshot",
}


def api_patterns(patterns, prefix=""):
    for pattern in patterns:
        route = prefix + str(pattern.pattern)
        if isinstance(pattern, URLResolver):
            yield from api_patterns(pattern.url_patterns, route)
        elif isinstance(pattern, URLPattern) and route.startswith("api/"):
            yield route, pattern


class ApiRouteSecurityTests(SimpleTestCase):
    def test_allow_any_routes_match_the_reviewed_public_allowlist(self):
        public_names = set()
        for route, pattern in api_patterns(get_resolver().url_patterns):
            view_class = getattr(pattern.callback, "view_class", None)
            self.assertIsNotNone(view_class, route)
            permissions = getattr(view_class, "permission_classes", ())
            if AllowAny in permissions:
                public_names.add(pattern.name)

        self.assertEqual(public_names, PUBLIC_API_ROUTE_NAMES)

    def test_every_api_route_has_a_four_role_permission_matrix(self):
        principals = {
            "anonymous": SimpleNamespace(is_authenticated=False, role=None),
            "client": SimpleNamespace(
                is_authenticated=True,
                role=User.Role.CLIENT,
            ),
            "representative": SimpleNamespace(
                is_authenticated=True,
                role=User.Role.REPRESENTATIVE,
            ),
            "admin": SimpleNamespace(
                is_authenticated=True,
                role=User.Role.ADMIN,
            ),
        }
        checked = 0
        for route, pattern in api_patterns(get_resolver().url_patterns):
            view_class = pattern.callback.view_class
            permission_classes = tuple(view_class.permission_classes)
            self.assertTrue(permission_classes, route)
            role_permissions = [
                permission
                for permission in permission_classes
                if issubclass(permission, HasRole)
            ]
            is_public = AllowAny in permission_classes
            requires_auth = any(
                issubclass(permission, IsAuthenticated)
                for permission in permission_classes
            )
            self.assertTrue(is_public or requires_auth or role_permissions, route)

            view = view_class()
            methods = [
                method.upper()
                for method in view_class.http_method_names
                if method not in {"head", "options"} and hasattr(view, method)
            ]
            for method in methods:
                matrix = {}
                for label, principal in principals.items():
                    principal.Role = User.Role
                    request = SimpleNamespace(user=principal, method=method)
                    matrix[label] = all(
                        permission().has_permission(request, view)
                        for permission in permission_classes
                    )
                if is_public:
                    self.assertTrue(all(matrix.values()), f"{route} [{method}]")
                else:
                    self.assertFalse(
                        matrix["anonymous"],
                        f"{route} [{method}]",
                    )
                    self.assertTrue(
                        any(value for label, value in matrix.items() if label != "anonymous"),
                        f"{route} [{method}] denies every authenticated role",
                    )
                if role_permissions:
                    for label, principal in principals.items():
                        expected = principal.is_authenticated and all(
                            principal.role in permission.allowed_roles
                            for permission in role_permissions
                        )
                        self.assertEqual(
                            matrix[label],
                            expected,
                            f"{route} [{method}/{label}]",
                        )
            checked += 1

        self.assertGreater(checked, 200)
