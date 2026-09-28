import struct
from io import BytesIO
from types import SimpleNamespace

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework import serializers

from .campaign_media import (
    CAMPAIGN_VIDEO_MAX_SIZE,
    mp4_duration_seconds,
    validate_campaign_video,
)


def atom(kind, payload):
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


def video_upload(seconds=5, *, version=0):
    if version == 0:
        timing = b"\0" * 8 + struct.pack(">II", 1000, seconds * 1000)
    else:
        timing = b"\0" * 16 + struct.pack(">IQ", 1000, seconds * 1000)
    mvhd = bytes([version]) + b"\0" * 3 + timing
    content = atom(b"ftyp", b"isom\0\0\x02\0isom") + atom(b"moov", atom(b"mvhd", mvhd))
    return SimpleUploadedFile("intro.mp4", content, content_type="video/mp4")


class CampaignMediaValidationTests(SimpleTestCase):
    def test_valid_mp4_duration_is_checked_and_read_position_is_restored(self):
        for version in (0, 1):
            with self.subTest(version=version):
                upload = video_upload(version=version)
                upload.seek(3)
                self.assertEqual(mp4_duration_seconds(upload), 5)
                self.assertEqual(upload.tell(), 3)
                self.assertIs(validate_campaign_video(upload), upload)

    def test_rejects_disguised_corrupt_long_and_oversized_videos(self):
        invalid = SimpleUploadedFile("intro.mp4", b"not an mp4", content_type="video/mp4")
        with self.assertRaisesMessage(serializers.ValidationError, "not a valid MP4"):
            validate_campaign_video(invalid)
        with self.assertRaisesMessage(serializers.ValidationError, "30 seconds"):
            validate_campaign_video(video_upload(seconds=31))
        with self.assertRaisesMessage(serializers.ValidationError, "Upload an MP4"):
            validate_campaign_video(SimpleUploadedFile("intro.txt", b"x", content_type="text/plain"))
        large = SimpleNamespace(name="intro.mp4", content_type="video/mp4", size=CAMPAIGN_VIDEO_MAX_SIZE + 1)
        with self.assertRaisesMessage(serializers.ValidationError, "15 MB"):
            validate_campaign_video(large)

    def test_rejects_missing_or_malformed_timing_atoms(self):
        fragments = (
            b"",
            atom(b"ftyp", b"isom"),
            atom(b"moov", atom(b"trak", b"")),
            atom(b"moov", atom(b"mvhd", b"\x02\0\0\0" + b"\0" * 16)),
            atom(b"moov", atom(b"mvhd", b"\0\0\0\0" + b"\0" * 8 + struct.pack(">II", 0, 5000))),
        )
        for content in fragments:
            with self.subTest(content=content[:12]):
                self.assertIsNone(mp4_duration_seconds(BytesIO(content)))
