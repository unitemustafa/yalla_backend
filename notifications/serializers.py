from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "audience",
            "type",
            "title",
            "message",
            "order_id",
            "is_read",
            "is_blocking",
            "is_resolved",
            "read_at",
            "resolved_at",
            "created_at",
        )
