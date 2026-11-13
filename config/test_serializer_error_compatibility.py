from django.test import SimpleTestCase
from rest_framework import serializers


class ListValidationErrorCompatibilityTests(SimpleTestCase):
    def test_many_validation_errors_preserve_item_positions_for_existing_clients(self):
        class ItemSerializer(serializers.Serializer):
            quantity = serializers.IntegerField(min_value=1)

        serializer = ItemSerializer(
            data=[{"quantity": 2}, {"quantity": 0}], many=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIsInstance(serializer.errors, list)
        self.assertEqual(serializer.errors[0], {})
        self.assertIn("quantity", serializer.errors[1])
