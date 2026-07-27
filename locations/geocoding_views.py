from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.views import IsAdminRole

from .geocoding import (
    GeoapifyRateLimited,
    GeoapifyUnavailable,
    autocomplete,
    city_coverage,
    reverse,
)


class AutocompleteQuerySerializer(serializers.Serializer):
    q = serializers.CharField(min_length=3, max_length=200, trim_whitespace=True)
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)
    lang = serializers.ChoiceField(choices=("ar", "en"), default="ar")


class ReverseQuerySerializer(serializers.Serializer):
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)
    lang = serializers.ChoiceField(choices=("ar", "en"), default="ar")


class CityCoverageQuerySerializer(serializers.Serializer):
    q = serializers.CharField(min_length=2, max_length=100, trim_whitespace=True)
    lang = serializers.ChoiceField(choices=("ar", "en"), default="ar")


class _GeoapifyView(APIView):
    permission_classes = [IsAuthenticated]
    rate_limit_scopes = ("geocoding_user",)

    def provider_response(self, operation):
        try:
            return operation()
        except GeoapifyRateLimited as error:
            response = Response(
                {
                    "code": "geocoding_rate_limited",
                    "detail": "Too many geocoding requests. Try again shortly.",
                    "retry_after_seconds": error.retry_after_seconds,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
            response["Retry-After"] = str(error.retry_after_seconds)
            return response
        except GeoapifyUnavailable:
            return Response(
                {
                    "code": "geocoding_unavailable",
                    "detail": "Location search is temporarily unavailable.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class GeocodingAutocompleteView(_GeoapifyView):
    def get(self, request):
        serializer = AutocompleteQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data
        result = self.provider_response(
            lambda: autocomplete(
                query=params["q"],
                latitude=params["latitude"],
                longitude=params["longitude"],
                language=params["lang"],
                request=request,
            )
        )
        return (
            result
            if isinstance(result, Response)
            else Response({"items": result})
        )


class GeocodingReverseView(_GeoapifyView):
    def get(self, request):
        serializer = ReverseQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data
        result = self.provider_response(
            lambda: reverse(
                latitude=params["latitude"],
                longitude=params["longitude"],
                language=params["lang"],
                request=request,
            )
        )
        return (
            result
            if isinstance(result, Response)
            else Response({"location": result})
        )


class CityCoverageLookupView(_GeoapifyView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        serializer = CityCoverageQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data
        result = self.provider_response(
            lambda: city_coverage(
                query=params["q"],
                language=params["lang"],
                request=request,
            )
        )
        if isinstance(result, Response):
            return result
        if result is None:
            return Response(
                {
                    "code": "city_not_found",
                    "detail": "تعذر العثور على نطاق واضح لهذه المدينة داخل مصر.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"coverage": result})
