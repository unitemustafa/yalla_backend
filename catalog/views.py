from rest_framework import status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from .serializers import AdditionClassificationSerializer


class IsAdminRole(BasePermission):
    message = "Only admin users can manage catalog data."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.ADMIN
        )


class AdditionClassificationCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request):
        serializer = AdditionClassificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        classification = serializer.save()
        return Response(
            AdditionClassificationSerializer(classification).data,
            status=status.HTTP_201_CREATED,
        )
