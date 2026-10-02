from config.media_test_tools import FFMPEG, FFPROBE
from datetime import timedelta
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import tempfile
import struct
from unittest.mock import patch

from celery.exceptions import Retry

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APITestCase

from config.video_processing import InvalidVideo
from .media_jobs import publish_pending_job
from .models import AppLaunchMedia, MediaJob


User = get_user_model()
JOBS_URL = "/api/v1/dashboard/media-jobs/"


class MediaJobTests(APITestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="yalla-media-job-test-")
        self.settings = override_settings(
            MEDIA_ROOT=self.media_root,
            PRIVATE_MEDIA_ROOT=str(Path(self.media_root) / "private"),
            FFMPEG_BINARY=str(FFMPEG),
            FFPROBE_BINARY=str(FFPROBE),
        )
        self.settings.enable()
        self.admin = User.objects.create_user(
            username="media_job_admin", email="media-job@example.com",
            phone="+201000009001", password="Password1!", role=User.Role.ADMIN,
        )
        self.client.force_authenticate(self.admin)

    def tearDown(self):
        self.settings.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def real_video_upload(self, *, name="video.mp4", total_size=None):
        if not FFMPEG.is_file() or not FFPROBE.is_file():
            self.skipTest("The portable FFmpeg test tools are unavailable.")
        path = Path(self.media_root) / name
        subprocess.run([
            str(FFMPEG), "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
            "color=c=green:s=320x180:r=24:d=1", "-c:v", "mpeg4", str(path),
        ], check=True, stdin=subprocess.DEVNULL)
        content = path.read_bytes()
        if total_size is not None and len(content) < total_size:
            padding = total_size - len(content)
            content += struct.pack(">I4s", padding, b"free") + b"\0" * (padding - 8)
        return SimpleUploadedFile(name, content, content_type="video/mp4")

    def ready_job(self, *, slot="market_login"):
        job = MediaJob.objects.create(owner=self.admin, slot=slot, state=MediaJob.State.READY)
        job.video.save("prepared.mp4", ContentFile(b"prepared"), save=False)
        job.poster.save("poster.png", self.png_content(), save=False)
        job.save(update_fields=["video", "poster"])
        return job

    def png_content(self):
        image = BytesIO()
        Image.new("RGB", (8, 8), "blue").save(image, format="PNG")
        return ContentFile(image.getvalue())

    @patch("dashboard.media_jobs.dispatch_job")
    def test_create_api_keeps_source_private_and_hides_urls_until_ready(self, dispatch):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(JOBS_URL, {
                "slot": "market_login", "file": self.real_video_upload(),
            }, format="multipart")

        self.assertEqual(response.status_code, 202, response.data)
        job = MediaJob.objects.get(pk=response.data["id"])
        self.assertEqual(job.state, MediaJob.State.PENDING)
        self.assertTrue(job.source.name.startswith("media-jobs/sources/"))
        self.assertIsNone(response.data["video_url"])
        self.assertIsNone(response.data["poster_url"])
        dispatch.assert_called_once_with(job.pk)

    def test_pending_job_does_not_replace_published_login_until_it_is_ready(self):
        launch = AppLaunchMedia.objects.create()
        launch.market_login_video.save("old.mp4", ContentFile(b"old-video"), save=False)
        launch.market_login_poster.save("old.png", self.png_content(), save=False)
        launch.save()
        old_video_name = launch.market_login_video.name
        job = MediaJob.objects.create(owner=self.admin, slot="market_login", state=MediaJob.State.PENDING)
        launch.market_login_pending_job = job
        launch.save(update_fields=["market_login_pending_job"])

        launch.refresh_from_db()
        self.assertEqual(launch.market_login_video.name, old_video_name)

        job = self.ready_job(slot="market_login")
        launch.market_login_pending_job = job
        launch.save(update_fields=["market_login_pending_job"])
        publish_pending_job(job)

        launch.refresh_from_db()
        self.assertEqual(launch.market_login_video.name, job.video.name)
        self.assertIsNone(launch.market_login_pending_job)

    @patch("dashboard.tasks.prepare_video")
    def test_cancelled_job_cannot_be_published_by_a_stale_worker(self, prepare):
        job = MediaJob.objects.create(owner=self.admin, slot="market_login")
        job.source.save("source.mp4", ContentFile(b"source"), save=True)
        launch = AppLaunchMedia.objects.create(market_login_pending_job=job)
        launch.market_login_video.save("published.mp4", ContentFile(b"published"), save=True)
        published_name = launch.market_login_video.name

        def cancel_during_prepare(source, directory):
            current = MediaJob.objects.get(pk=job.pk)
            current.cancelled, current.state = True, MediaJob.State.FAILED
            current.save(update_fields=["cancelled", "state"])
            video, poster = Path(directory) / "video.mp4", Path(directory) / "poster.png"
            video.write_bytes(b"new-video")
            poster.write_bytes(b"new-poster")
            return video, poster, {"duration": 1}

        prepare.side_effect = cancel_during_prepare
        from .tasks import process_media_job
        process_media_job.apply(args=[str(job.pk)])

        job.refresh_from_db()
        launch.refresh_from_db()
        self.assertTrue(job.cancelled)
        self.assertEqual(job.state, MediaJob.State.FAILED)
        self.assertEqual(launch.market_login_video.name, published_name)
        self.assertEqual(launch.market_login_pending_job_id, job.pk)

    def test_ready_only_api_and_stats_report_stalled_jobs(self):
        pending = MediaJob.objects.create(owner=self.admin, slot="campaign")
        ready = self.ready_job(slot="campaign")
        MediaJob.objects.filter(pk=pending.pk).update(created_at=timezone.now() - timedelta(minutes=11))

        pending_response = self.client.get(f"{JOBS_URL}{pending.pk}/")
        ready_response = self.client.get(f"{JOBS_URL}{ready.pk}/")
        stats = self.client.get(f"{JOBS_URL}stats/")

        self.assertEqual(pending_response.status_code, 200)
        self.assertIsNone(pending_response.data["video_url"])
        self.assertIsNone(pending_response.data["poster_url"])
        self.assertIsNotNone(ready_response.data["video_url"])
        self.assertIsNotNone(ready_response.data["poster_url"])
        self.assertEqual(stats.status_code, 200)
        self.assertEqual(stats.data["counts"]["pending"], 1)
        self.assertEqual(stats.data["counts"]["ready"], 1)
        self.assertEqual(stats.data["stalled"], 1)

    @patch("dashboard.tasks.prepare_video", side_effect=InvalidVideo("bad stream"))
    def test_invalid_video_failure_is_permanent_and_not_retried(self, prepare):
        job = MediaJob.objects.create(owner=self.admin, slot="campaign")
        job.source.save("source.mp4", ContentFile(b"source"), save=True)

        from .tasks import process_media_job
        result = process_media_job.apply(args=[str(job.pk)])

        job.refresh_from_db()
        self.assertEqual(result.state, "SUCCESS")
        self.assertEqual(job.state, MediaJob.State.FAILED)
        self.assertEqual(job.error_code, "invalid_video")
        self.assertEqual(job.attempt, 1)
        prepare.assert_called_once()

    @patch("dashboard.tasks.prepare_video", side_effect=OSError("storage down"))
    def test_storage_failure_retries_only_twice(self, prepare):
        job = MediaJob.objects.create(owner=self.admin, slot="campaign")
        job.source.save("source.mp4", ContentFile(b"source"), save=True)

        from .tasks import process_media_job
        with self.assertRaises(Retry):
            process_media_job.apply(args=[str(job.pk)])
        job.refresh_from_db()
        final = process_media_job.apply(args=[str(job.pk)], retries=2)

        job.refresh_from_db()
        self.assertEqual(job.state, MediaJob.State.FAILED)
        self.assertEqual(job.error_code, "storage_unavailable")
        self.assertEqual(job.attempt, 2)
        self.assertEqual(final.state, "SUCCESS")
        self.assertEqual(prepare.call_count, 2)

    def test_newer_pending_job_prevents_an_older_ready_job_from_publishing(self):
        launch = AppLaunchMedia.objects.create()
        old = self.ready_job(slot="market_login")
        newer = MediaJob.objects.create(owner=self.admin, slot="market_login")
        launch.market_login_pending_job = newer
        launch.save(update_fields=["market_login_pending_job"])

        publish_pending_job(old)

        launch.refresh_from_db()
        self.assertEqual(launch.market_login_pending_job_id, newer.pk)
        self.assertFalse(launch.market_login_video)

    @patch("dashboard.tasks.prepare_video", side_effect=OSError("storage down"))
    def test_fresh_dispatches_cannot_reset_the_automatic_retry_budget(self, prepare):
        job = MediaJob.objects.create(owner=self.admin, slot="campaign")
        job.source.save("source.mp4", ContentFile(b"source"), save=True)
        from .tasks import process_media_job
        for _ in range(2):
            with self.assertRaises(Retry):
                process_media_job.apply(args=[str(job.pk)])
        final = process_media_job.apply(args=[str(job.pk)])
        job.refresh_from_db()
        self.assertEqual(final.state, "SUCCESS")
        self.assertEqual(job.state, MediaJob.State.FAILED)
        self.assertEqual(job.metadata["storage_retries"], 2)
        self.assertEqual(job.attempt, 3)
        self.assertEqual(prepare.call_count, 3)

    @patch("dashboard.media_views.dispatch_job")
    def test_cancel_and_retry_endpoints_only_retry_retryable_uncancelled_job(self, dispatch):
        failed = MediaJob.objects.create(
            owner=self.admin, slot="campaign", state=MediaJob.State.FAILED,
            error_code="storage_unavailable",
        )
        failed.source.save("source.mp4", ContentFile(b"source"), save=True)
        with self.captureOnCommitCallbacks(execute=True):
            retried = self.client.post(f"{JOBS_URL}{failed.pk}/retry/", format="json")

        failed.refresh_from_db()
        self.assertEqual(retried.status_code, 202, retried.data)
        self.assertEqual(failed.state, MediaJob.State.PENDING)
        dispatch.assert_called_once_with(failed.pk)
        cancelled = self.client.delete(f"{JOBS_URL}{failed.pk}/")
        failed.refresh_from_db()
        denied = self.client.post(f"{JOBS_URL}{failed.pk}/retry/", format="json")
        self.assertEqual(cancelled.status_code, 204)
        self.assertTrue(failed.cancelled)
        self.assertEqual(denied.status_code, 400)

    def test_login_api_rejects_pending_and_campaign_jobs(self):
        pending = MediaJob.objects.create(owner=self.admin, slot="market_login")
        wrong_slot = self.ready_job(slot="campaign")

        pending_response = self.client.patch("/api/v1/dashboard/app-media/", {
            "video_job_id": str(pending.pk),
        }, format="json")
        wrong_slot_response = self.client.patch("/api/v1/dashboard/app-media/", {
            "video_job_id": str(wrong_slot.pk),
        }, format="json")

        self.assertEqual(pending_response.status_code, 400)
        self.assertIn("video_job_id", pending_response.data)
        self.assertEqual(wrong_slot_response.status_code, 400)
        self.assertIn("video_job_id", wrong_slot_response.data)

    @patch("dashboard.media_jobs.dispatch_job")
    def test_real_padded_mp4_above_eight_mb_and_near_thirty_mb_are_accepted(self, dispatch):
        sizes = (9 * 1024 * 1024, 29 * 1024 * 1024)
        for size in sizes:
            with self.subTest(size=size), self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(JOBS_URL, {
                    "slot": "campaign", "file": self.real_video_upload(total_size=size),
                }, format="multipart")

            self.assertEqual(response.status_code, 202, response.data)
            self.assertEqual(MediaJob.objects.get(pk=response.data["id"]).source.size, size)
        self.assertEqual(dispatch.call_count, 2)

    @patch("dashboard.media_jobs.dispatch_job")
    def test_source_over_thirty_mb_returns_file_error_before_the_body_limit(self, dispatch):
        response = self.client.post(JOBS_URL, {
            "slot": "campaign", "file": self.real_video_upload(total_size=30 * 1024 * 1024 + 1),
        }, format="multipart")

        self.assertEqual(response.status_code, 400)
        self.assertIn("file", response.data)
        self.assertIn("30 MB", str(response.data["file"]))
        dispatch.assert_not_called()
