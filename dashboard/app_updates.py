"""APK publishing and public release discovery for the courier Android app."""

import hashlib
import zipfile

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdminRole
from .models import DeliveryAppRelease

MAX_APK_BYTES = 100_000_000


class DeliveryAppReleaseSerializer(serializers.ModelSerializer):
    version_code = serializers.IntegerField(min_value=1, max_value=2_100_000_000)
    apk = serializers.FileField(write_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryAppRelease
        fields = (
            "id", "version_code", "version_name", "release_notes", "apk",
            "download_url", "sha256", "file_size", "is_active", "created_at",
        )
        read_only_fields = ("id", "sha256", "file_size", "created_at", "is_active")

    def get_download_url(self, release):
        return self.context["request"].build_absolute_uri(release.apk.url)

    def validate_version_code(self, value):
        if DeliveryAppRelease.objects.filter(version_code=value).exists():
            raise serializers.ValidationError("رقم البناء مستخدم بالفعل.")
        return value

    def validate_apk(self, upload):
        if not upload.name.lower().endswith(".apk"):
            raise serializers.ValidationError("اختر ملف APK لتطبيق أندرويد.")
        if not 0 < upload.size <= MAX_APK_BYTES:
            raise serializers.ValidationError("حجم الملف يجب ألا يتجاوز 100 MB.")
        try:
            with zipfile.ZipFile(upload) as archive:
                entries = archive.infolist()
                names = {entry.filename for entry in entries}
                if len(entries) > 20_000 or "AndroidManifest.xml" not in names:
                    raise ValueError("Invalid APK contents")
                if "classes.dex" not in names:
                    raise ValueError("Missing Android code")
                if archive.getinfo("AndroidManifest.xml").file_size > 2_000_000:
                    raise ValueError("Invalid Android manifest")
        except (zipfile.BadZipFile, OSError, ValueError, KeyError) as exc:
            raise serializers.ValidationError("الملف ليس حزمة APK صالحة.") from exc
        finally:
            upload.seek(0)
        digest = hashlib.sha256()
        for chunk in upload.chunks():
            digest.update(chunk)
        upload.seek(0)
        self._apk_sha256 = digest.hexdigest()
        return upload

    def create(self, validated_data):
        validated_data["sha256"] = self._apk_sha256
        validated_data["file_size"] = validated_data["apk"].size
        release = DeliveryAppRelease(**validated_data)
        try:
            with transaction.atomic():
                release.save()
        except IntegrityError as exc:
            # File storage is outside the DB transaction.
            if release.apk and release.apk._committed:
                release.apk.delete(save=False)
            raise serializers.ValidationError(
                {"version_code": "رقم البناء مستخدم بالفعل. استخدم رقمًا أعلى."}
            ) from exc
        return release


class DeliveryAppReleasesView(APIView):
    permission_classes = (IsAuthenticated, IsAdminRole)
    parser_classes = (MultiPartParser, FormParser)

    def get(self, request):
        releases = DeliveryAppRelease.objects.order_by("-version_code")[:50]
        return Response(DeliveryAppReleaseSerializer(
            releases, many=True, context={"request": request},
        ).data)

    def post(self, request):
        serializer = DeliveryAppReleaseSerializer(
            data=request.data, context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        release = serializer.save(created_by=request.user)
        return Response(DeliveryAppReleaseSerializer(
            release, context={"request": request},
        ).data, status=status.HTTP_201_CREATED)


class DeliveryAppReleaseStatusView(APIView):
    permission_classes = (IsAuthenticated, IsAdminRole)

    def patch(self, request, release_id):
        release = get_object_or_404(DeliveryAppRelease, pk=release_id)
        if not isinstance(request.data, dict) or set(request.data) != {"is_active"}:
            raise serializers.ValidationError({"is_active": "حدد حالة النشر فقط."})
        release.is_active = serializers.BooleanField().run_validation(request.data["is_active"])
        release.save(update_fields=["is_active"])
        return Response(DeliveryAppReleaseSerializer(
            release, context={"request": request},
        ).data)


class LatestDeliveryAppReleaseView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()

    def get(self, request):
        field = serializers.IntegerField(min_value=1, max_value=2_100_000_000)
        installed = field.run_validation(request.query_params.get("version_code"))
        release = DeliveryAppRelease.objects.filter(
            is_active=True, version_code__gt=installed,
        ).order_by("-version_code").first()
        data = None if release is None else DeliveryAppReleaseSerializer(
            release, context={"request": request},
        ).data
        return Response({"update": data}, headers={"Cache-Control": "no-store"})
