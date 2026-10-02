"""Portable FFmpeg paths for real-file tests on CI and developer machines."""
import os
import shutil
from pathlib import Path


def binary(name):
    configured = os.environ.get(f"{name.upper()}_BINARY", name)
    resolved = shutil.which(configured)
    if resolved:
        return Path(resolved)
    portable = Path(os.environ.get("TEMP", "/tmp")) / "yalla-media-tools" / f"{name}.exe"
    if portable.is_file():
        return portable
    # CI installs these tools explicitly; missing tools fail the media tests.
    return Path(configured)


FFMPEG = binary("ffmpeg")
FFPROBE = binary("ffprobe")
