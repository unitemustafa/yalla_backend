from rest_framework import serializers

from .models import PartnerApplication


class PartnerApplicationSerializer(serializers.ModelSerializer):
    applicant_id = serializers.IntegerField(read_only=True)
    applicant_username = serializers.CharField(
        source="applicant.username",
        read_only=True,
    )
    applicant_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PartnerApplication
        fields = (
            "id",
            "applicant_id",
            "applicant_username",
            "applicant_name",
            "business_name",
            "contact_first_name",
            "contact_last_name",
            "business_type",
            "branches_count",
            "applicant_role",
            "has_trade_license",
            "email",
            "mobile_number",
            "landline",
            "whatsapp_opt_in",
            "notes",
            "status",
            "admin_notes",
            "reviewed_by_name",
            "reviewed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "applicant_id",
            "applicant_username",
            "applicant_name",
            "status",
            "admin_notes",
            "reviewed_by_name",
            "reviewed_at",
            "created_at",
            "updated_at",
        )

    def get_applicant_name(self, instance):
        return instance.applicant.get_full_name().strip() or instance.applicant.username

    def get_reviewed_by_name(self, instance):
        reviewer = instance.reviewed_by
        if reviewer is None:
            return None
        return reviewer.get_full_name().strip() or reviewer.username

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            has_open_application = PartnerApplication.objects.filter(
                applicant=user,
                status__in=(
                    PartnerApplication.Status.PENDING,
                    PartnerApplication.Status.IN_REVIEW,
                ),
            ).exists()
            if has_open_application:
                raise serializers.ValidationError(
                    {
                        "detail": (
                            "You already have a partner application under review."
                        )
                    }
                )
        return attrs


class PartnerApplicationAdminUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PartnerApplication
        fields = ("status", "admin_notes")

    def validate_status(self, value):
        if value not in PartnerApplication.Status.values:
            raise serializers.ValidationError("Invalid partner application status.")
        return value

