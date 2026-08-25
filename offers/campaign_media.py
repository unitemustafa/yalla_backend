import struct

from rest_framework import serializers

from config.image_validation import validate_safe_image


CAMPAIGN_IMAGE_MAX_SIZE = 5 * 1024 * 1024
CAMPAIGN_VIDEO_MAX_SIZE = 15 * 1024 * 1024
CAMPAIGN_VIDEO_MAX_SECONDS = 30
CAMPAIGN_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
CAMPAIGN_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def validate_campaign_image(value):
    name = value.name or ""
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    content_type = (getattr(value, "content_type", "") or "").lower()
    if extension not in CAMPAIGN_IMAGE_EXTENSIONS:
        raise serializers.ValidationError("Upload a JPG, JPEG, PNG, or WEBP image.")
    if content_type not in CAMPAIGN_IMAGE_CONTENT_TYPES:
        raise serializers.ValidationError("Unsupported campaign image type.")
    if value.size > CAMPAIGN_IMAGE_MAX_SIZE:
        raise serializers.ValidationError("Campaign images must be 5 MB or smaller.")
    return validate_safe_image(value)


def _atom_header(stream, limit):
    start = stream.tell()
    if start + 8 > limit:
        return None
    header = stream.read(8)
    if len(header) != 8:
        return None
    size, atom_type = struct.unpack(">I4s", header)
    header_size = 8
    if size == 1:
        extended = stream.read(8)
        if len(extended) != 8:
            return None
        size = struct.unpack(">Q", extended)[0]
        header_size = 16
    elif size == 0:
        size = limit - start
    if size < header_size or start + size > limit:
        return None
    return atom_type, stream.tell(), start + size


def _find_atom(stream, start, end, target):
    stream.seek(start)
    while stream.tell() < end:
        atom = _atom_header(stream, end)
        if atom is None:
            return None
        atom_type, payload_start, atom_end = atom
        if atom_type == target:
            return payload_start, atom_end
        stream.seek(atom_end)
    return None


def mp4_duration_seconds(value):
    current = value.tell()
    try:
        value.seek(0, 2)
        file_size = value.tell()
        moov = _find_atom(value, 0, file_size, b"moov")
        if moov is None:
            return None
        mvhd = _find_atom(value, moov[0], moov[1], b"mvhd")
        if mvhd is None:
            return None
        value.seek(mvhd[0])
        version_raw = value.read(1)
        if not version_raw:
            return None
        version = version_raw[0]
        value.read(3)
        if version == 0:
            value.read(8)
            timescale_raw = value.read(4)
            duration_raw = value.read(4)
            if len(timescale_raw) != 4 or len(duration_raw) != 4:
                return None
            timescale = struct.unpack(">I", timescale_raw)[0]
            duration = struct.unpack(">I", duration_raw)[0]
        elif version == 1:
            value.read(16)
            timescale_raw = value.read(4)
            duration_raw = value.read(8)
            if len(timescale_raw) != 4 or len(duration_raw) != 8:
                return None
            timescale = struct.unpack(">I", timescale_raw)[0]
            duration = struct.unpack(">Q", duration_raw)[0]
        else:
            return None
        if timescale <= 0:
            return None
        return duration / timescale
    finally:
        value.seek(current)


def validate_campaign_video(value):
    name = value.name or ""
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    content_type = (getattr(value, "content_type", "") or "").lower()
    if extension != "mp4" or content_type != "video/mp4":
        raise serializers.ValidationError("Upload an MP4 video.")
    if value.size > CAMPAIGN_VIDEO_MAX_SIZE:
        raise serializers.ValidationError("Campaign videos must be 15 MB or smaller.")
    value.seek(0)
    header = value.read(12)
    value.seek(0)
    if len(header) < 12 or header[4:8] != b"ftyp":
        raise serializers.ValidationError("The uploaded file is not a valid MP4 video.")
    duration = mp4_duration_seconds(value)
    if duration is None:
        raise serializers.ValidationError("Could not read the MP4 video duration.")
    if duration > CAMPAIGN_VIDEO_MAX_SECONDS:
        raise serializers.ValidationError("Campaign videos must be 30 seconds or shorter.")
    return value
