from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from accounts.permissions import IsAdminRole
from config.media_specs import media_contract
from .media_jobs import create_media_job, dispatch_job, job_data
from .models import MediaJob
from .media_api_serializers import MediaContractSerializer, MediaJobUploadSerializer, MediaJobStatusSerializer, MediaJobStatsSerializer


class MediaSpecsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(responses=MediaContractSerializer)
    def get(self, request):
        return Response(media_contract())


class MediaJobCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(request=MediaJobUploadSerializer, responses={202: MediaJobStatusSerializer})
    def post(self, request):
        slot, upload = request.data.get("slot"), request.FILES.get("file")
        if slot not in {"market_login", "campaign"} or upload is None:
            raise serializers.ValidationError({"file": "Choose a video and a supported media slot."})
        with transaction.atomic():
            try:
                job = create_media_job(upload, request.user, slot)
            except serializers.ValidationError as exc:
                raise serializers.ValidationError({"file": exc.detail}) from exc
        return Response(job_data(job, request), status=status.HTTP_202_ACCEPTED)


class MediaJobDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(responses=MediaJobStatusSerializer)
    def get(self, request, job_id):
        return Response(job_data(get_object_or_404(MediaJob, pk=job_id), request))

    @extend_schema(responses={204: None})
    def delete(self, request, job_id):
        with transaction.atomic():
            job = get_object_or_404(MediaJob.objects.select_for_update(), pk=job_id)
            job.cancelled = True
            job.state, job.error_code = "failed", "cancelled"
            job.error, job.completed_at = "Processing was cancelled.", timezone.now()
            job.attempt_token = None
            job.save()
            job.applaunchmedia_set.update(market_login_pending_job=None)
            job.homecampaign_set.update(pending_video_job=None)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MediaJobRetryView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(request=None, responses={202: MediaJobStatusSerializer})
    def post(self, request, job_id):
        with transaction.atomic():
            job = get_object_or_404(MediaJob.objects.select_for_update(), pk=job_id)
            if not job_data(job)["retryable"] or job.cancelled or not job.source:
                raise serializers.ValidationError({"job": "This upload cannot be retried. Upload a new file."})
            job.state, job.error, job.error_code = "pending", "", ""
            job.started_at, job.completed_at, job.attempt_token = None, None, None
            job.metadata = {}
            job.save()
            transaction.on_commit(lambda: dispatch_job(job.pk))
        return Response(job_data(job, request), status=status.HTTP_202_ACCEPTED)


class MediaJobStatsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    @extend_schema(responses=MediaJobStatsSerializer)
    def get(self, request):
        cutoff = timezone.now() - timedelta(minutes=10)
        return Response({"counts": {state: MediaJob.objects.filter(state=state, cancelled=False).count() for state in MediaJob.State.values},
                         "stalled": MediaJob.objects.filter(Q(state="pending", created_at__lt=cutoff) | Q(state="processing", started_at__lt=cutoff), cancelled=False).count(),
                         "alert_after_seconds": 600})
