from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.views import IsAdminRole
from notifications.models import Notification

from .models import PartnerApplication
from .serializers import (
    PartnerApplicationAdminUpdateSerializer,
    PartnerApplicationSerializer,
)


def _partner_notification(application):
    return Notification.objects.create(
        audience=Notification.Audience.ADMIN,
        type=Notification.Type.NEW_PARTNER_APPLICATION,
        title="طلب شراكة جديد",
        message=f"تم استلام طلب شراكة جديد من {application.business_name}.",
        data={
            "partner_application_id": application.id,
            "business_name": application.business_name,
            "applicant_id": application.applicant_id,
        },
    )


class PartnerApplicationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        applications = (
            PartnerApplication.objects.filter(applicant=request.user)
            .select_related("applicant", "reviewed_by")
            .order_by("-created_at", "-id")
        )
        return Response(
            PartnerApplicationSerializer(
                applications,
                many=True,
                context={"request": request},
            ).data
        )

    @transaction.atomic
    def post(self, request):
        if request.user.role != User.Role.CLIENT:
            return Response(
                {"detail": "Only client accounts can apply as partners."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = PartnerApplicationSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        application = serializer.save(applicant=request.user)
        _partner_notification(application)
        return Response(
            PartnerApplicationSerializer(
                application,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )


class AdminPartnerApplicationListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        applications = PartnerApplication.objects.select_related(
            "applicant",
            "reviewed_by",
        )
        requested_status = request.query_params.get("status", "").strip()
        if requested_status:
            applications = applications.filter(status=requested_status)

        search = request.query_params.get("search", "").strip()
        if search:
            applications = applications.filter(
                Q(business_name__icontains=search)
                | Q(contact_first_name__icontains=search)
                | Q(contact_last_name__icontains=search)
                | Q(email__icontains=search)
                | Q(mobile_number__icontains=search)
            )

        return Response(
            PartnerApplicationSerializer(
                applications,
                many=True,
                context={"request": request},
            ).data
        )


class AdminPartnerApplicationDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    @transaction.atomic
    def patch(self, request, application_id):
        application = (
            PartnerApplication.objects.select_for_update()
            .select_related("applicant", "reviewed_by")
            .filter(pk=application_id)
            .first()
        )
        if application is None:
            return Response(
                {"detail": "Partner application not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PartnerApplicationAdminUpdateSerializer(
            application,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        next_status = serializer.validated_data.get("status", application.status)
        final_statuses = {
            PartnerApplication.Status.APPROVED,
            PartnerApplication.Status.REJECTED,
        }
        serializer.save(
            reviewed_by=request.user,
            reviewed_at=timezone.now() if next_status in final_statuses else None,
        )

        if next_status in final_statuses:
            now = timezone.now()
            Notification.objects.filter(
                audience=Notification.Audience.ADMIN,
                type=Notification.Type.NEW_PARTNER_APPLICATION,
                data__partner_application_id=application.id,
                is_resolved=False,
            ).update(
                is_resolved=True,
                resolved_at=now,
                updated_at=now,
            )

        application.refresh_from_db()
        return Response(
            PartnerApplicationSerializer(
                application,
                context={"request": request},
            ).data
        )

