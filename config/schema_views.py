from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from accounts.permissions import IsAdminRole


class AdminSchemaView(SpectacularAPIView):
    permission_classes = (IsAdminRole,)


class AdminDocsView(SpectacularSwaggerView):
    permission_classes = (IsAdminRole,)
