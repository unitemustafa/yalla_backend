from rest_framework import serializers

from catalog.models import Product, ProductCategory, ProductVariant
from offers.models import Offer

from .models import Market, MarketClassification


class HomeMarketSerializer(serializers.ModelSerializer):
    classification_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Market
        fields = ("id", "name", "branch", "status", "classification_id")


class HomeMarketClassificationSerializer(serializers.ModelSerializer):
    markets = serializers.SerializerMethodField()

    class Meta:
        model = MarketClassification
        fields = ("id", "name", "markets")

    def get_markets(self, classification):
        eligible_market_ids = self.context["eligible_market_ids"]
        markets = classification.markets.filter(
            id__in=eligible_market_ids,
            status=Market.Status.ACTIVE,
        ).order_by("name")
        return HomeMarketSerializer(markets, many=True).data


class HomeCategorySerializer(serializers.ModelSerializer):
    classification_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProductCategory
        fields = (
            "id",
            "name",
            "type",
            "description",
            "image",
            "classification_id",
        )


class HomeVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ("id", "price", "sku")


class HomeProductSerializer(serializers.ModelSerializer):
    category = HomeCategorySerializer(read_only=True)
    market = HomeMarketSerializer(read_only=True)
    variants = HomeVariantSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "description",
            "image",
            "discount",
            "category",
            "market",
            "variants",
        )


class HomeOfferSerializer(serializers.ModelSerializer):
    market = HomeMarketSerializer(read_only=True)
    products = HomeProductSerializer(many=True, read_only=True)

    class Meta:
        model = Offer
        fields = (
            "id",
            "title",
            "description",
            "image",
            "type",
            "discount",
            "start_time",
            "end_time",
            "active_days",
            "use_limits",
            "user_limit",
            "status",
            "market",
            "products",
        )
