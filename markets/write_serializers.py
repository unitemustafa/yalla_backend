from django.db import transaction
from django.db.models import Q
from rest_framework import serializers

from catalog.models import Product
from locations.models import ServiceCity

from .models import Market, MarketSubcategory


class AdminMarketWriteMixin:
    def validate(self, attrs):
        self._validate_required_fields(attrs)
        self._validate_delivery_times(attrs)
        self._validate_relation_aliases()
        self._validate_subcategories(attrs.get("subcategory_ids"))
        self._validate_market_types(
            attrs.get("market_types"),
            attrs.get(
                "classification",
                getattr(self.instance, "classification", None),
            ),
        )
        self._validate_market_scope(attrs)
        return attrs

    def _validate_required_fields(self, attrs):
        if self.instance is not None:
            return
        required_errors = {}
        if not attrs.get("image"):
            required_errors["image"] = "Store logo is required."
        if not attrs.get("cover_image"):
            required_errors["cover_image"] = "Store cover image is required."
        if attrs.get("delivery_time_min_minutes") is None:
            required_errors["delivery_time_min_minutes"] = (
                "Minimum delivery time is required."
            )
        if attrs.get("delivery_time_max_minutes") is None:
            required_errors["delivery_time_max_minutes"] = (
                "Maximum delivery time is required."
            )
        if required_errors:
            raise serializers.ValidationError(required_errors)

    def _validate_delivery_times(self, attrs):
        minimum_delivery_time = attrs.get(
            "delivery_time_min_minutes",
            getattr(self.instance, "delivery_time_min_minutes", None),
        )
        maximum_delivery_time = attrs.get(
            "delivery_time_max_minutes",
            getattr(self.instance, "delivery_time_max_minutes", None),
        )
        if (minimum_delivery_time is None) != (maximum_delivery_time is None):
            raise serializers.ValidationError(
                {
                    "delivery_time_max_minutes": (
                        "Both delivery time values must be provided together."
                    )
                }
            )
        if (
            minimum_delivery_time is not None
            and maximum_delivery_time < minimum_delivery_time
        ):
            raise serializers.ValidationError(
                {
                    "delivery_time_max_minutes": (
                        "Maximum delivery time cannot be less than the minimum."
                    )
                }
            )

    def _validate_relation_aliases(self):
        if (
            "delivery_areas" in self.initial_data
            and "delivery_area_ids" in self.initial_data
        ):
            raise serializers.ValidationError(
                {
                    "delivery_areas": (
                        "Use either delivery_areas or delivery_area_ids, not both."
                    )
                }
            )
        if (
            "service_cities" in self.initial_data
            and "service_city_ids" in self.initial_data
        ):
            raise serializers.ValidationError(
                {
                    "service_cities": (
                        "Use either service_cities or service_city_ids, not both."
                    )
                }
            )

    def _raw_relation_ids(self, field_name):
        if hasattr(self.initial_data, "getlist"):
            raw_ids = self.initial_data.getlist(field_name)
        else:
            raw_ids = self.initial_data.get(field_name, [])
        if not isinstance(raw_ids, (list, tuple)):
            raw_ids = [raw_ids]
        return [str(value) for value in raw_ids]

    def _validate_subcategories(self, selected_subcategories):
        if selected_subcategories is None:
            return

        normalized_raw_ids = self._raw_relation_ids("subcategory_ids")
        if len(normalized_raw_ids) != len(set(normalized_raw_ids)):
            raise serializers.ValidationError(
                {"subcategory_ids": "Subcategories must be unique."}
            )
        existing_ids = (
            set(
                self.instance.subcategory_assignments.values_list(
                    "subcategory_id",
                    flat=True,
                )
            )
            if self.instance is not None
            else set()
        )
        newly_added = [
            subcategory
            for subcategory in selected_subcategories
            if subcategory.id not in existing_ids
        ]
        if any(not subcategory.is_active for subcategory in newly_added):
            raise serializers.ValidationError(
                {
                    "subcategory_ids": (
                        "Only active store subcategories can be assigned."
                    )
                }
            )
        if self.instance is None:
            return

        selected_ids = {subcategory.id for subcategory in selected_subcategories}
        removed_ids = existing_ids - selected_ids
        if (
            removed_ids
            and Product.objects.filter(
                market=self.instance,
            ).filter(
                Q(subcategory_id__in=removed_ids)
                | Q(subcategories__id__in=removed_ids)
            ).distinct().exists()
        ):
            raise serializers.ValidationError(
                {
                    "subcategory_ids": (
                        "Move products to another subcategory before "
                        "removing it from this market."
                    )
                }
            )

    def _validate_market_types(
        self,
        selected_market_types,
        prospective_classification,
    ):
        if selected_market_types is not None:
            normalized_type_ids = self._raw_relation_ids("market_type_ids")
            if len(normalized_type_ids) != len(set(normalized_type_ids)):
                raise serializers.ValidationError(
                    {"market_type_ids": "Market types must be unique."}
                )
            invalid_types = [
                market_type
                for market_type in selected_market_types
                if (
                    not market_type.is_active
                    or market_type.classification_id
                    != getattr(prospective_classification, "id", None)
                )
            ]
            if invalid_types:
                raise serializers.ValidationError(
                    {
                        "market_type_ids": (
                            "Only active market types from the selected "
                            "classification can be assigned."
                        )
                    }
                )
            return

        if (
            self.instance is not None
            and prospective_classification is not None
            and prospective_classification.id != self.instance.classification_id
            and self.instance.market_types.exclude(
                classification=prospective_classification
            ).exists()
        ):
            raise serializers.ValidationError(
                {
                    "market_type_ids": (
                        "Select market types that belong to the new classification."
                    )
                }
            )

    def _validate_market_scope(self, attrs):
        scope = attrs.get(
            "scope",
            getattr(self.instance, "scope", Market.Scope.SERVICE_CITY),
        )
        service_cities = attrs.get("service_cities")
        delivery_areas = attrs.get("delivery_areas")
        if service_cities is None and delivery_areas is not None:
            service_cities = list(
                ServiceCity.objects.filter(
                    delivery_areas__in=delivery_areas,
                    is_active=True,
                ).distinct()
            )
            attrs["service_cities"] = service_cities

        if scope == Market.Scope.GENERAL:
            if service_cities:
                raise serializers.ValidationError(
                    {
                        "service_city_ids": (
                            "General markets cannot target a service city."
                        )
                    }
                )
            attrs["service_cities"] = []
            return

        existing_count = (
            self.instance.service_cities.count()
            if self.instance is not None and service_cities is None
            else 0
        )
        if service_cities is not None:
            if not service_cities:
                raise serializers.ValidationError(
                    {"service_city_ids": "At least one service city is required."}
                )
            if len(service_cities) > 1:
                raise serializers.ValidationError(
                    {"service_city_ids": "Only one service city may be selected."}
                )
        elif existing_count > 1:
            raise serializers.ValidationError(
                {"service_city_ids": "Only one service city may be selected."}
            )
        elif self.instance is None or existing_count == 0:
            raise serializers.ValidationError(
                {"service_city_ids": "At least one service city is required."}
            )

    @transaction.atomic
    def create(self, validated_data):
        send_notification = validated_data.pop("send_notification", False)
        delivery_areas = validated_data.pop("delivery_areas", [])
        service_cities = validated_data.pop("service_cities", [])
        subcategories = validated_data.pop("subcategory_ids", [])
        market_types = validated_data.pop("market_types", [])
        market = Market.objects.create(**validated_data)
        market.service_cities.set(service_cities)
        market.delivery_areas.set(delivery_areas)
        self._replace_subcategories(market, subcategories)
        market.market_types.set(market_types)
        if send_notification:
            from notifications.market_services import (
                create_market_notification_intent,
            )

            request = self.context.get("request")
            requested_by_id = (
                request.user.id
                if request is not None and request.user.is_authenticated
                else None
            )
            create_market_notification_intent(market, requested_by_id)
        return market

    def update(self, instance, validated_data):
        validated_data.pop("send_notification", None)
        delivery_areas = validated_data.pop("delivery_areas", None)
        service_cities = validated_data.pop("service_cities", None)
        subcategories = validated_data.pop("subcategory_ids", None)
        market_types = validated_data.pop("market_types", None)
        instance = super().update(instance, validated_data)
        if service_cities is not None:
            instance.service_cities.set(service_cities)
        if delivery_areas is not None:
            instance.delivery_areas.set(delivery_areas)
        if subcategories is not None:
            self._replace_subcategories(instance, subcategories)
        if market_types is not None:
            instance.market_types.set(market_types)
        return instance

    def _replace_subcategories(self, market, subcategories):
        market.subcategory_assignments.all().delete()
        MarketSubcategory.objects.bulk_create(
            MarketSubcategory(
                market=market,
                subcategory=subcategory,
                sort_order=index,
            )
            for index, subcategory in enumerate(subcategories)
        )
        if hasattr(market, "_prefetched_objects_cache"):
            market._prefetched_objects_cache.pop(
                "subcategory_assignments",
                None,
            )
