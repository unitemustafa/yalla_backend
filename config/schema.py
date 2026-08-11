import re

from rest_framework import serializers
from rest_framework.generics import GenericAPIView
from rest_framework.views import APIView

from drf_spectacular.openapi import AutoSchema


class UndocumentedPayloadSerializer(serializers.Serializer):
    """Visible placeholder until a legacy APIView receives explicit contracts."""


class YallaAutoSchema(AutoSchema):
    """Keep legacy APIViews visible while explicit annotations are added."""

    def get_operation_id(self):
        operation_id = super().get_operation_id()
        # drf-spectacular deliberately removes path parameter names while
        # tokenizing paths. Several legacy APIViews expose list and detail
        # handlers with the same base path, so retain those parameter names to
        # keep generated client method names stable and collision-free.
        parameters = re.findall(r"{([^}:]+)(?::[^}]+)?}", self.path)
        if parameters:
            return f"{operation_id}_by_{'_and_'.join(parameters)}"
        return operation_id

    def _get_serializer(self):
        view = self.view
        if (
            isinstance(view, APIView)
            and not isinstance(view, GenericAPIView)
            and not callable(getattr(view, "get_serializer", None))
            and not callable(getattr(view, "get_serializer_class", None))
            and not hasattr(view, "serializer_class")
        ):
            return UndocumentedPayloadSerializer(context={"request": self.view.request})
        return super()._get_serializer()


def remove_duplicate_optional_slash_routes(endpoints):
    """Document one canonical path when runtime supports both slash variants."""

    actual = {
        (path, method)
        for path, _path_regex, method, _callback in endpoints
    }
    filtered = []
    for endpoint in endpoints:
        path, _path_regex, method, _callback = endpoint
        if not path.endswith("/") and (f"{path}/", method) in actual:
            continue
        filtered.append(endpoint)
    return filtered
