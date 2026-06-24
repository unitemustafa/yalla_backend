from rest_framework import serializers

from .models import AdditionClassification


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
