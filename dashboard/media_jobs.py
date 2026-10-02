import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.db import transaction
from botocore.exceptions import BotoCoreError, ClientError
from rest_framework import serializers
from rest_framework.exceptions import APIException

from config.media_specs import VIDEO_MAX_BYTES
from config.video_processing import InvalidVideo, VideoToolsUnavailable, probe_video
from .models import MediaJob

logger = logging.getLogger(__name__)


class MediaUnavailable(APIException):
    status_code = 503
    default_detail = "Video processing is temporarily unavailable. Please retry later."


def validate_video_upload(upload):
    if Path(upload.name or "").suffix.lower() != ".mp4" or getattr(upload, "content_type", "") != "video/mp4":
        raise serializers.ValidationError("Upload an MP4 video.")
    if upload.size > VIDEO_MAX_BYTES:
        raise serializers.ValidationError("Videos must be 30 MB or smaller.")
    position = upload.tell()
    try:
        with TemporaryDirectory(prefix="yalla-probe-") as directory:
            path = Path(directory) / "input.mp4"
            upload.seek(0)
            with path.open("wb") as target:
                for chunk in upload.chunks():
                    target.write(chunk)
            probe_video(path)
    except InvalidVideo as exc:
        raise serializers.ValidationError(str(exc)) from exc
    except (VideoToolsUnavailable, OSError) as exc:
        raise MediaUnavailable() from exc
    finally:
        upload.seek(position)
    return upload


def dispatch_job(job_id):
    from .tasks import process_media_job
    try:
        process_media_job.delay(str(job_id))
    except Exception:
        # The periodic dispatcher will recover pending jobs after broker outages.
        logger.warning("media_job_dispatch_failed job_id=%s", job_id)


def create_media_job(upload, owner, slot, *, validated=False, poster=None):
    if not validated:
        validate_video_upload(upload)
    job = MediaJob(owner=owner, slot=slot)
    try:
        job.source.save(f"{uuid4().hex}.mp4", upload, save=False)
        if poster is not None:
            job.custom_poster.save("poster.png", poster, save=False)
        job.save()
    except Exception as exc:
        for field in (job.source, job.custom_poster):
            if field and field._committed:
                try:
                    field.storage.delete(field.name)
                except (OSError, BotoCoreError, ClientError):
                    logger.warning("media_job_source_cleanup_failed job_id=%s", job.pk)
        if isinstance(exc, (OSError, BotoCoreError, ClientError)):
            raise MediaUnavailable() from exc
        raise
    transaction.on_commit(lambda: dispatch_job(job.pk))
    return job


def ready_job(job_id, slot, *, lock=False):
    try:
        queryset = MediaJob.objects.select_for_update() if lock else MediaJob.objects
        job = queryset.get(pk=job_id, slot=slot, state="ready", cancelled=False)
    except (MediaJob.DoesNotExist, ValueError) as exc:
        raise serializers.ValidationError({"video_job_id": "The video must finish processing before publication."}) from exc
    if not job.video or not job.poster:
        raise serializers.ValidationError({"video_job_id": "The prepared video is unavailable."})
    return job


def job_data(job, request=None):
    def url(field):
        if job.state != "ready" or job.cancelled or not field:
            return None
        return request.build_absolute_uri(field.url) if request else field.url
    return {"id": str(job.pk), "slot": job.slot, "state": job.state,
            "cancelled": job.cancelled, "error": job.error, "error_code": job.error_code,
            "retryable": bool(job.source) and job.state == "failed" and not job.cancelled and job.error_code in {"storage_unavailable", "tools_unavailable", "worker_interrupted"},
            "video_url": url(job.video), "poster_url": url(job.poster),
            "metadata": job.metadata, "created_at": job.created_at,
            "started_at": job.started_at, "completed_at": job.completed_at}


def apply_ready_job(target, job, *, poster=None):
    if job.cancelled or job.state != "ready":
        raise serializers.ValidationError({"video_job_id": "Video is not ready."})
    if job.slot == "market_login":
        target.market_login_video = job.video.name
        target.market_login_poster = poster if poster is not None else job.poster.name
        target.market_login = None
        target.market_login_pending_job = None
    else:
        target.video = job.video.name
        target.video_poster = poster if poster is not None else job.poster.name
        target.media_type = "video"
        target.sheet_image = None
        target.pending_video_job = None
    target.save()
    return target


def publish_pending_job(job):
    # Detached jobs are never published automatically. Legacy inline uploads
    # publish only while the target still points to this exact request.
    from offers.models import HomeCampaign
    from .models import AppLaunchMedia
    for model, field in ((AppLaunchMedia, "market_login_pending_job"), (HomeCampaign, "pending_video_job")):
        target = model.objects.select_for_update().filter(**{field: job}).first()
        if target is not None:
            apply_ready_job(target, job)
