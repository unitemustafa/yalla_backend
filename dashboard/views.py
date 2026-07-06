from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.views import IsAdminRole

from .models import DashboardSettings
from .serializers import (
    DashboardOverviewSerializer,
    DashboardRangeQuerySerializer,
    DashboardSettingsSerializer,
)
from .services import build_dashboard_overview


class DashboardOverviewView(APIView):
    permission_classes = (IsAuthenticated, IsAdminRole)

    def get(self, request):
        query = DashboardRangeQuerySerializer(
            data={
                "from_date": request.query_params.get("from"),
                "to_date": request.query_params.get("to"),
            }
        )
        query.is_valid(raise_exception=True)
        overview = build_dashboard_overview(
            query.validated_data["from"],
            query.validated_data["to"],
        )
        return Response(DashboardOverviewSerializer(overview).data)


class DashboardSettingsView(APIView):
    permission_classes = (IsAuthenticated, IsAdminRole)
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    def get_object(self):
        settings, _ = DashboardSettings.objects.get_or_create(pk=1)
        return settings

    def get(self, request):
        settings = self.get_object()
        serializer = DashboardSettingsSerializer(
            settings,
            context={"request": request},
        )
        return Response(serializer.data)

    def patch(self, request):
        settings = self.get_object()
        serializer = DashboardSettingsSerializer(
            settings,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        settings = serializer.save()
        return Response(
            DashboardSettingsSerializer(
                settings,
                context={"request": request},
            ).data
        )
