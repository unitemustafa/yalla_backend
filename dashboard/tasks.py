import logging
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from celery import shared_task
from django.core.files import File
from django.db import transaction
from django.utils import timezone
from botocore.exceptions import BotoCoreError, ClientError

from config.video_processing import InvalidVideo, VideoToolsUnavailable, prepare_video
from .media_jobs import dispatch_job, publish_pending_job
from .models import MediaJob

logger = logging.getLogger(__name__)


@shared_task(bind=True, queue="media", max_retries=2, soft_time_limit=140, time_limit=160)
def process_media_job(self, job_id):
    token = uuid4()
    with transaction.atomic():
        job = MediaJob.objects.select_for_update().filter(pk=job_id).first()
        if job is None or job.cancelled or job.state != "pending":
            return
        job.state, job.started_at, job.attempt_token = "processing", timezone.now(), token
        job.attempt += 1
        job.save(update_fields=["state", "started_at", "attempt", "attempt_token"])
    saved = []
    try:
        with TemporaryDirectory(prefix="yalla-video-") as directory:
            source = Path(directory) / "source.mp4"
            with job.source.open("rb") as original, source.open("wb") as target:
                for chunk in original.chunks():
                    target.write(chunk)
            video, poster, metadata = prepare_video(source, directory)
            with video.open("rb") as prepared:
                job.video.save("video.mp4", File(prepared), save=False)
                saved.append((job.video.storage, job.video.name))
            with (job.custom_poster.open("rb") if job.custom_poster else poster.open("rb")) as prepared:
                job.poster.save("poster.png", File(prepared), save=False)
                saved.append((job.poster.storage, job.poster.name))
        with transaction.atomic():
            current = MediaJob.objects.select_for_update().get(pk=job_id)
            if current.cancelled or current.state != "processing" or current.attempt_token != token:
                return
            current.video, current.poster = job.video.name, job.poster.name
            current.metadata, current.state = metadata, "ready"
            current.error, current.error_code, current.completed_at = "", "", timezone.now()
            current.save()
            publish_pending_job(current)
        saved.clear()
        logger.info("media_job_ready job_id=%s duration_seconds=%s", job_id, metadata["duration"])
    except Exception as exc:
        if isinstance(exc, InvalidVideo):
            code, message = "invalid_video", str(exc)
        elif isinstance(exc, VideoToolsUnavailable):
            code, message = "tools_unavailable", "Video processing is temporarily unavailable."
        elif isinstance(exc, (OSError, BotoCoreError, ClientError)):
            code, message = "storage_unavailable", "Media storage is temporarily unavailable."
        else:
            code, message = "worker_interrupted", "Video processing was interrupted."
        # Beat may dispatch a fresh Celery message while a retry is pending.
        # Persist the budget so a new message cannot reset it indefinitely.
        storage_retries = job.metadata.get("storage_retries", 0)
        retryable = code == "storage_unavailable" and storage_retries < 2 and self.request.retries < 2
        failure_metadata = {**job.metadata, "storage_retries": storage_retries + int(retryable)}
        updated = MediaJob.objects.filter(pk=job_id, attempt_token=token, cancelled=False, state="processing").update(
            state="pending" if retryable else "failed", error=message, error_code=code,
            completed_at=None if retryable else timezone.now(),
            metadata=failure_metadata,
        )
        logger.warning("media_job_failed job_id=%s code=%s attempt=%s", job_id, code, job.attempt)
        if retryable and updated:
            raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
    finally:
        for storage, name in saved:
            from config.media_cleanup import schedule_storage_cleanup
            schedule_storage_cleanup(storage, name)


@shared_task(queue="default")
def monitor_media_jobs():
    cutoff = timezone.now() - timedelta(minutes=10)
    for job in MediaJob.objects.filter(state__in=["pending", "processing"], cancelled=False):
        if (job.started_at or job.created_at) < cutoff:
            logger.error("media_job_stalled job_id=%s state=%s", job.pk, job.state)
            if job.state == "processing":
                MediaJob.objects.filter(pk=job.pk, state="processing", attempt_token=job.attempt_token).update(
                    state="failed", error_code="worker_interrupted", error="The processing worker stopped. Retry the upload.",
                    completed_at=timezone.now(), attempt_token=None,
                )
        if job.state == "pending":
            dispatch_job(job.pk)
    counts = {state: MediaJob.objects.filter(state=state, cancelled=False).count() for state in MediaJob.State.values}
    logger.info("media_job_counts %s", counts)
    return counts


@shared_task(queue="default")
def cleanup_due_media():
    from config.media_cleanup import get_storage_by_identifier, delete_storage_file_if_unreferenced
    from .models import MediaCleanup
    now = timezone.now()
    # Keep source files through the retry window, then release job references.
    for job in MediaJob.objects.filter(state__in=["ready", "failed"], completed_at__lt=now - timedelta(hours=24)):
        if job.applaunchmedia_set.exists() or job.homecampaign_set.exists():
            continue
        if job.source or job.custom_poster or job.video or job.poster:
            job.source, job.custom_poster, job.video, job.poster = "", "", "", ""
            job.save(update_fields=["source", "custom_poster", "video", "poster"])
    for cleanup in MediaCleanup.objects.filter(delete_after__lte=now).iterator():
        try:
            delete_storage_file_if_unreferenced(get_storage_by_identifier(cleanup.storage_id), cleanup.name)
            cleanup.delete()
        except (OSError, BotoCoreError, ClientError):
            logger.warning("media_cleanup_storage_unavailable cleanup_id=%s", cleanup.pk)
