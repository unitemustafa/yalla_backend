"""Bounded, local-file-only video probing and preparation."""
import json
import math
import struct
import subprocess
import time
from fractions import Fraction
from pathlib import Path

from django.conf import settings

from .media_specs import VIDEO_MAX_SECONDS, VIDEO_OUTPUT_MAX_BYTES


class InvalidVideo(ValueError):
    pass


class VideoToolsUnavailable(RuntimeError):
    pass


def _run(arguments, *, timeout=15):
    try:
        return subprocess.run(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=True, timeout=timeout).stdout
    except FileNotFoundError as exc:
        raise VideoToolsUnavailable("Video processing tools are unavailable.") from exc
    except subprocess.TimeoutExpired as exc:
        raise InvalidVideo("Video processing exceeded its time limit.") from exc
    except subprocess.CalledProcessError as exc:
        # Do not return decoder output or storage paths to clients.
        raise InvalidVideo("The video is corrupted or cannot be decoded.") from exc


def probe_video(path, *, output=False, timeout=15):
    raw = _run([getattr(settings, "FFPROBE_BINARY", "ffprobe"), "-v", "error",
                "-protocol_whitelist", "file,pipe", "-f", "mov", "-show_format",
                "-show_streams", "-of", "json", str(Path(path).resolve())], timeout=timeout)
    try:
        data = json.loads(raw)
        streams = data["streams"]
        videos = [stream for stream in streams if stream.get("codec_type") == "video" and not stream.get("disposition", {}).get("attached_pic")]
        if len(videos) != 1:
            raise ValueError
        video = videos[0]
        duration = float(data["format"]["duration"])
        width, height = int(video["width"]), int(video["height"])
        rate = float(Fraction(video.get("avg_frame_rate") or video.get("r_frame_rate", "0")))
        if not math.isfinite(duration) or not 0 < duration <= VIDEO_MAX_SECONDS:
            raise InvalidVideo("Video duration must be greater than zero and at most 30 seconds.")
        if min(width, height) < 2 or max(width, height) > 12000 or width * height > 25_000_000 or not 0 < rate <= 240 or not video.get("codec_name"):
            raise InvalidVideo("Video dimensions or frame rate are unsupported.")
        audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
        rotation = float(next((side["rotation"] for side in video.get("side_data_list", []) if "rotation" in side), video.get("tags", {}).get("rotate", 0)))
        if not math.isfinite(rotation) or abs(rotation) > 36000:
            raise InvalidVideo("Video rotation is unsupported.")
        if output and (video["codec_name"] != "h264" or video.get("pix_fmt") != "yuv420p" or max(width, height) > 1280 or rate > 30.01 or rotation % 360 != 0 or len(audios) > 1 or any(audio.get("codec_name") != "aac" for audio in audios)):
            raise InvalidVideo("The prepared video does not match the playback contract.")
        if output:
            _validate_faststart(path)
        return {"duration": duration, "width": width, "height": height,
                "frame_rate": rate, "codec": video["codec_name"], "has_audio": bool(audios), "rotation": rotation % 360}
    except (KeyError, TypeError, ValueError, ZeroDivisionError, json.JSONDecodeError) as exc:
        if isinstance(exc, InvalidVideo):
            raise
        raise InvalidVideo("Upload a valid MP4 containing a playable video stream.") from exc


def _validate_faststart(path):
    """Read only top-level box headers; never load a whole video into memory."""
    length = Path(path).stat().st_size
    moov_seen = False
    with Path(path).open("rb") as content:
        while content.tell() < length:
            offset = content.tell()
            header = content.read(8)
            if len(header) != 8:
                break
            size, kind = struct.unpack(">I4s", header)
            header_size = 8
            if size == 1:
                extended = content.read(8)
                if len(extended) != 8:
                    break
                size, header_size = struct.unpack(">Q", extended)[0], 16
            elif size == 0:
                size = length - offset
            if size < header_size or offset + size > length:
                break
            if kind == b"moov":
                moov_seen = True
            if kind == b"mdat":
                if moov_seen:
                    return
                break
            content.seek(offset + size)
    raise InvalidVideo("The prepared MP4 must contain faststart metadata before its video data.")


def prepare_video(source, directory):
    deadline = time.monotonic() + 120

    def remaining():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise InvalidVideo("Video processing exceeded its time limit.")
        return seconds

    metadata = probe_video(source, timeout=min(15, remaining()))
    video = Path(directory) / "prepared.mp4"
    poster = Path(directory) / "poster.png"
    binary = getattr(settings, "FFMPEG_BINARY", "ffmpeg")
    _run([binary, "-nostdin", "-v", "error", "-xerror", "-err_detect", "explode", "-y", "-protocol_whitelist", "file,pipe",
          "-f", "mov", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?",
          "-vf", f"scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,fps={min(metadata['frame_rate'], 30)}",
          "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
          "-profile:v", "main", "-maxrate", "3M", "-bufsize", "6M", "-threads", "2",
          "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-map_metadata", "-1",
          "-movflags", "+faststart", str(video)], timeout=remaining())
    if video.stat().st_size > VIDEO_OUTPUT_MAX_BYTES:
        raise InvalidVideo("The prepared video exceeds 15 MB. Use a simpler or shorter video.")
    result = probe_video(video, output=True, timeout=min(15, remaining()))
    _run([binary, "-nostdin", "-v", "error", "-y", "-protocol_whitelist", "file,pipe",
          "-ss", str(min(1, result["duration"] / 2)), "-i", str(video), "-frames:v", "1",
          "-threads", "1", str(poster)], timeout=remaining())
    return video, poster, result
