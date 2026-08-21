from rest_framework.permissions import BasePermission, IsAuthenticated, SAFE_METHODS

from .models import User


class HasRole(BasePermission):
    """Authenticate against the application's role model, not Django staff flags."""

    allowed_roles = frozenset()

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        return bool(
            user
            and user.is_authenticated
            and user.role in self.allowed_roles
        )


class IsAdminRole(HasRole):
    message = "Only admin users can manage users."
    allowed_roles = frozenset({User.Role.ADMIN})


class IsCatalogAdminRole(IsAdminRole):
    message = "Only admin users can manage catalog data."


class IsMarketAdminRole(IsAdminRole):
    message = "Only admin users can manage markets."


class IsOrderAdminRole(IsAdminRole):
    message = "Only admin users can manage orders."


class IsClientRole(HasRole):
    message = "Only client users can update client information."
    allowed_roles = frozenset({User.Role.CLIENT})


class IsCatalogClientRole(IsClientRole):
    message = "Only client users can like products."


class IsMarketClientRole(IsClientRole):
    message = "Only client users can access address products."


class IsOrderClientRole(IsClientRole):
    message = "Only client users can access their orders."


class IsRepresentativeRole(HasRole):
    message = "Only courier users can access courier orders."
    allowed_roles = frozenset({User.Role.REPRESENTATIVE})


# Compatibility name for existing imports while the codebase standardizes on
# "representative" internally and keeps /courier/ as the public API path.
IsCourierRole = IsRepresentativeRole


class DeliveryAreaPermission(IsAuthenticated):
    """Allow authenticated reads and reserve area mutations for admin role."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role == User.Role.ADMIN
