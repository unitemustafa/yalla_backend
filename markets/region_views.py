from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from locations.models import ServiceCity

from .region import (
    compact_market_region_selection,
    current_market_region_selection,
    detect_service_city,
    service_city_payload,
    service_city_region_selection,
)
from .region_serializers import (
    MarketRegionDetectSerializer,
    MarketRegionUpdateSerializer,
)


class MarketRegionOptionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        options = [
            {
                "mode": User.MarketRegionMode.GENERAL,
                "label": User.MarketRegionMode.GENERAL.label,
                "service_city": None,
            }
        ]
        options.extend(
            {
                "mode": User.MarketRegionMode.SERVICE_CITY,
                "label": city.name,
                "service_city": service_city_payload(city),
            }
            for city in ServiceCity.objects.filter(is_active=True).order_by(
                "name",
                "id",
            )
        )
        return Response(
            {
                "options": options,
                "current_selection": current_market_region_selection(
                    request.user
                ),
            }
        )


class MarketRegionMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "current_selection": current_market_region_selection(
                    request.user
                )
            }
        )

    def patch(self, request):
        serializer = MarketRegionUpdateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {"current_selection": current_market_region_selection(user)}
        )


class MarketRegionDetectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MarketRegionDetectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        latitude = serializer.validated_data["latitude"]
        longitude = serializer.validated_data["longitude"]
        detected_city = detect_service_city(latitude, longitude)
        current_selection = compact_market_region_selection(request.user)

        if detected_city is None:
            return Response(
                {
                    "action": "unsupported_location",
                    "current_selection": current_selection,
                    "detected_region": None,
                    "message": (
                        "Your current location is outside available service "
                        "cities. Please choose a region manually."
                    ),
                }
            )

        detected_region = service_city_region_selection(detected_city)
        if current_selection is None:
            return Response(
                {
                    "action": "select_detected_region",
                    "current_selection": None,
                    "detected_region": detected_region,
                    "message": (
                        f"We detected {detected_city.name} as your current "
                        "market region."
                    ),
                }
            )

        if (
            current_selection["mode"] == User.MarketRegionMode.SERVICE_CITY
            and current_selection["service_city"]["id"] == detected_city.id
        ):
            return Response(
                {
                    "action": "same_region",
                    "current_selection": current_selection,
                    "detected_region": detected_region,
                    "message": (
                        "You are already in your selected market region."
                    ),
                }
            )

        return Response(
            {
                "action": "suggest_switch",
                "current_selection": current_selection,
                "detected_region": detected_region,
                "message": (
                    f"It looks like you are in {detected_city.name}. Do you "
                    "want to switch your market region?"
                ),
            }
        )
