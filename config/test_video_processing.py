"""Integration tests for the local, bounded FFmpeg media contract."""
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, override_settings

from .media_specs import VIDEO_MAX_SECONDS
from .media_test_tools import FFMPEG, FFPROBE
from .video_processing import InvalidVideo, prepare_video, probe_video




@override_settings(FFMPEG_BINARY=str(FFMPEG), FFPROBE_BINARY=str(FFPROBE))
class VideoProcessingTests(SimpleTestCase):
    """These deliberately use actual MP4s; atom-shaped byte fixtures are unsafe."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not FFMPEG.is_file() or not FFPROBE.is_file():
            raise cls.skipTest("The portable FFmpeg test tools are unavailable.")

    def make_video(self, directory, name, *, size="320x640", seconds=1, codec="mpeg4", audio=False):
        target = Path(directory) / name
        command = [
            str(FFMPEG), "-nostdin", "-v", "error", "-y", "-f", "lavfi",
            "-i", f"color=c=blue:s={size}:r=24:d={seconds}",
        ]
        if audio:
            command += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-shortest"]
        command += ["-c:v", codec]
        if audio:
            command += ["-c:a", "aac"]
        command += [str(target)]
        subprocess.run(command, check=True, stdin=subprocess.DEVNULL)
        return target

    def test_probe_accepts_real_portrait_video_without_audio(self):
        with TemporaryDirectory() as directory:
            source = self.make_video(directory, "portrait.mp4")

            metadata = probe_video(source)

        self.assertEqual(metadata["width"], 320)
        self.assertEqual(metadata["height"], 640)
        self.assertFalse(metadata["has_audio"])
        self.assertEqual(metadata["codec"], "mpeg4")

    def test_probe_rejects_corrupt_and_overlong_files(self):
        with TemporaryDirectory() as directory:
            corrupt = Path(directory) / "corrupt.mp4"
            corrupt.write_bytes(b"not an MP4")
            long_video = self.make_video(directory, "long.mp4", seconds=VIDEO_MAX_SECONDS + 1)

            with self.assertRaisesMessage(InvalidVideo, "corrupted"):
                probe_video(corrupt)
            with self.assertRaisesMessage(InvalidVideo, "at most 30 seconds"):
                probe_video(long_video)

    def test_prepare_transcodes_to_playback_contract_without_upscaling(self):
        with TemporaryDirectory() as directory:
            source = self.make_video(
                directory, "small-with-audio.mp4", size="320x180", codec="mpeg4", audio=True,
            )

            prepared, poster, metadata = prepare_video(source, directory)

            self.assertTrue(prepared.is_file())
            self.assertTrue(poster.is_file())
            self.assertEqual(metadata["codec"], "h264")
            self.assertEqual((metadata["width"], metadata["height"]), (320, 180))
            self.assertTrue(metadata["has_audio"])
            self.assertLessEqual(metadata["frame_rate"], 30)
            self.assertEqual(probe_video(prepared, output=True), metadata)

    def test_prepared_contract_rejects_mp4_without_faststart(self):
        with TemporaryDirectory() as directory:
            source = self.make_video(directory, "non-streaming.mp4", size="320x180", codec="libx264")
            with self.assertRaisesMessage(InvalidVideo, "faststart"):
                probe_video(source, output=True)

    def test_prepare_applies_rotation_and_bounds_large_sources(self):
        with TemporaryDirectory() as directory:
            source = self.make_video(directory, "landscape.mp4", size="1920x1080", codec="libx264")
            rotated = Path(directory) / "rotated.mp4"
            options = subprocess.run([str(FFMPEG), "-h", "full"], capture_output=True, check=True,
                                     stdin=subprocess.DEVNULL, timeout=15).stdout
            rotation = ["-display_rotation:v:0", "90"] if b"-display_rotation" in options else []
            command = [str(FFMPEG), "-nostdin", "-v", "error", "-y", *rotation, "-i", str(source), "-c", "copy"]
            if not rotation:
                command += ["-metadata:s:v:0", "rotate=90"]
            subprocess.run([*command, str(rotated)], check=True,
                           stdin=subprocess.DEVNULL)
            self.assertEqual(probe_video(rotated)["rotation"], 90)
            _, _, metadata = prepare_video(rotated, directory)
            self.assertEqual((metadata["width"], metadata["height"]), (720, 1280))
            self.assertEqual(metadata["rotation"], 0)
            self.assertFalse(metadata["has_audio"])
