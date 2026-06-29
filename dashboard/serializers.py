from rest_framework import serializers


class DashboardRangeQuerySerializer(serializers.Serializer):
    from_date = serializers.DateField(source="from")
    to_date = serializers.DateField(source="to")

    def validate(self, attrs):
        if attrs["from"] > attrs["to"]:
            raise serializers.ValidationError(
                {"to": "The to date must be on or after the from date."}
            )
        return attrs


class DashboardRangeSerializer(serializers.Serializer):
    from_date = serializers.DateField(source="from")
    to_date = serializers.DateField(source="to")
    timezone = serializers.CharField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        return {
            "from": data["from_date"],
            "to": data["to_date"],
            "timezone": data["timezone"],
        }


class RevenueSerializer(serializers.Serializer):
    total = serializers.DecimalField(max_digits=20, decimal_places=2)
    percentage = serializers.FloatField()


class OrderMetricsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    completed = serializers.IntegerField()
    incomplete = serializers.IntegerField()
    completion_rate = serializers.FloatField()


class CustomerMetricsSerializer(serializers.Serializer):
    new = serializers.IntegerField()
    returning = serializers.IntegerField()
    return_rate = serializers.FloatField()


class TopProductSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    name = serializers.CharField()
    revenue = serializers.DecimalField(max_digits=20, decimal_places=2)
    quantity_sold = serializers.IntegerField()
    orders_count = serializers.IntegerField()


class ActiveOrderCustomerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class ActiveOrderSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    number = serializers.CharField()
    customer = ActiveOrderCustomerSerializer()
    total = serializers.DecimalField(max_digits=20, decimal_places=2)
    status = serializers.CharField()
    created_at = serializers.DateTimeField()


class TopShopSerializer(serializers.Serializer):
    market_id = serializers.IntegerField()
    name = serializers.CharField()
    zone = serializers.CharField()
    orders_count = serializers.IntegerField()
    average_items_per_order = serializers.FloatField()
    revenue = serializers.DecimalField(max_digits=20, decimal_places=2)


class DashboardOverviewSerializer(serializers.Serializer):
    range = DashboardRangeSerializer()
    currency = serializers.CharField()
    revenue = RevenueSerializer()
    orders = OrderMetricsSerializer()
    customers = CustomerMetricsSerializer()
    top_products = TopProductSerializer(many=True)
    active_orders = ActiveOrderSerializer(many=True)
    top_shops = TopShopSerializer(many=True)
