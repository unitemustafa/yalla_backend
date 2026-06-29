from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.views import IsAdminRole

from .serializers import DashboardOverviewSerializer, DashboardRangeQuerySerializer
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
