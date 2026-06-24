from rest_framework import serializers

from .models import AdditionClassification, ProductAddition


class AdditionClassificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdditionClassification
        fields = ("id", "name")

    def validate_name(self, value):
        name = value.strip()
        if AdditionClassification.objects.filter(name__iexact=name).exists():
            raise serializers.ValidationError(
                "An addition classification with this name already exists."
            )
        return name


class ProductAdditionSerializer(serializers.ModelSerializer):
    classification_id = serializers.PrimaryKeyRelatedField(
        queryset=AdditionClassification.objects.all(),
        source="classification",
        write_only=True,
    )
    classification = AdditionClassificationSerializer(read_only=True)
    products = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = ProductAddition
        fields = (
            "id",
            "classification",
            "classification_id",
            "products",
            "image",
            "name_ar",
            "name_en",
            "price",
            "is_active",
        )

    def validate_name_ar(self, value):
        return value.strip()

    def validate_name_en(self, value):
        return value.strip()
