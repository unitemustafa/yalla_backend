"""Public API shapes; quarantine file paths are never part of a response."""
from rest_framework import serializers


class MediaJobUploadSerializer(serializers.Serializer):
    slot = serializers.ChoiceField(choices=["market_login", "campaign"])
    file = serializers.FileField()


class MediaJobStatusSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slot = serializers.CharField()
    state = serializers.ChoiceField(choices=["pending", "processing", "ready", "failed"])
    cancelled = serializers.BooleanField()
    error = serializers.CharField(allow_blank=True)
    error_code = serializers.CharField(allow_blank=True)
    retryable = serializers.BooleanField()
    video_url = serializers.URLField(allow_null=True)
    poster_url = serializers.URLField(allow_null=True)
    metadata = serializers.JSONField()
    created_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)


class MediaContractSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    images = serializers.DictField(child=serializers.JSONField())
    video = serializers.JSONField()


class MediaJobStatsSerializer(serializers.Serializer):
    counts = serializers.DictField(child=serializers.IntegerField())
    stalled = serializers.IntegerField()
    alert_after_seconds = serializers.IntegerField()
