import json

from django.db import transaction
from rest_framework import serializers

from markets.models import MarketSubcategory

from .models import (
    Product,
    ProductAttribute,
    ProductAttributeOption,
    ProductAttributeValue,
    ProductVariant,
    VariantAttributeValue,
)
from .product_images import (
    PRODUCT_IMAGE_MAX_COUNT,
    add_product_images,
    clear_primary_product_image,
)
from .serializer_utils import deduplicate_image_uploads


class AdminProductWriteMixin:
    def to_internal_value(self, data):
        if hasattr(data, "getlist"):
            uploads = data.getlist("images")
            normalized_data = {
                key: data.get(key)
                for key in data.keys()
                if key != "images"
            }
            if "additions" in data:
                normalized_data["additions"] = data.getlist("additions")
            if uploads:
                normalized_data["image_uploads"] = uploads
            data = normalized_data
        else:
            data = dict(data)
        if isinstance(data.get("images"), (list, tuple)):
            data["image_uploads"] = list(data["images"])
        for key in ("attributes", "variants", "attribute_values", "additions"):
            value = data.get(key)
            if key == "additions" and isinstance(value, list) and len(value) == 1:
                value = value[0]
            if isinstance(value, str):
                stripped = value.strip()
                if stripped.startswith("[") or stripped.startswith("{"):
                    try:
                        data[key] = json.loads(stripped)
                    except json.JSONDecodeError:
                        raise serializers.ValidationError(
                            {key: "Invalid JSON payload."}
                        )
                elif key == "additions":
                    data[key] = [value]
        return super().to_internal_value(data)

    def validate(self, attrs):
        repeated_uploads = list(attrs.get("image_uploads", []))
        legacy_image = attrs.get("image", serializers.empty)
        uploads = list(repeated_uploads)
        if legacy_image is not serializers.empty and legacy_image is not None:
            uploads.append(legacy_image)

        if uploads:
            unique_uploads, upload_indexes = deduplicate_image_uploads(uploads)
            attrs["image_uploads"] = unique_uploads

            primary_index = attrs.get("primary_image_index")
            if primary_index is not None:
                selectable_count = len(repeated_uploads) or len(uploads)
                if primary_index >= selectable_count:
                    raise serializers.ValidationError(
                        {"primary_image_index": "Invalid primary image index."}
                    )
                attrs["primary_image_index"] = upload_indexes[primary_index]
            elif legacy_image is not serializers.empty and not repeated_uploads:
                attrs["primary_image_index"] = upload_indexes[0]

            existing_count = self.instance.images.count() if self.instance else 0
            if existing_count + len(unique_uploads) > PRODUCT_IMAGE_MAX_COUNT:
                raise serializers.ValidationError(
                    {"images": "A product can have at most 10 images."}
                )
        elif "primary_image_index" in attrs:
            raise serializers.ValidationError(
                {"primary_image_index": "Upload images before selecting a primary."}
            )

        market = attrs.get("market") or getattr(self.instance, "market", None)
        subcategory = attrs.get("subcategory") or getattr(
            self.instance,
            "subcategory",
            None,
        )
        if market is not None and subcategory is not None:
            if not MarketSubcategory.objects.filter(
                market=market,
                subcategory=subcategory,
            ).exists():
                raise serializers.ValidationError(
                    {
                        "subcategory_id": (
                            "Subcategory must be assigned to the selected market."
                        )
                    }
                )
            unchanged_inactive = (
                self.instance is not None
                and self.instance.subcategory_id == subcategory.id
                and self.instance.market_id == market.id
            )
            if not subcategory.is_active and not unchanged_inactive:
                raise serializers.ValidationError(
                    {"subcategory_id": "Subcategory must be active."}
                )

        category = attrs.get("category") or getattr(self.instance, "category", None)
        legacy_attribute_values = attrs.get("attribute_values", [])
        if legacy_attribute_values and category is not None:
            self._validate_legacy_attribute_values(legacy_attribute_values, category)
        attributes = attrs.get("attributes")
        variants = attrs.get("variants")
        if attributes is not None:
            self._validate_attribute_payload(attributes)
        if variants is not None:
            for variant in variants:
                legacy_values = variant.get("attribute_values", [])
                if legacy_values and category is not None:
                    self._validate_legacy_attribute_values(legacy_values, category)
            self._validate_variant_payload(attributes, variants)
        self._validate_sale_variants(attrs, variants)
        return attrs

    def _validate_sale_variants(self, attrs, variants):
        is_available = attrs.get(
            "is_available",
            self.instance.is_available if self.instance is not None else True,
        )

        if variants is not None:
            has_valid_variant = bool(variants) and all(
                variant.get("price") is not None and variant["price"] >= 0
                for variant in variants
            )
        elif self.instance is not None:
            has_valid_variant = self.instance.variants.filter(price__gte=0).exists()
        else:
            has_valid_variant = False

        if is_available and not has_valid_variant:
            raise serializers.ValidationError(
                {"variants": self.SALE_VARIANT_ERROR}
            )

        if is_available and "attributes" in attrs and variants is None:
            raise serializers.ValidationError(
                {"variants": self.SALE_VARIANT_ERROR}
            )

        if variants is not None and any(
            variant.get("price") is None or variant["price"] < 0
            for variant in variants
        ):
            raise serializers.ValidationError(
                {"variants": self.SALE_VARIANT_ERROR}
            )

    def _validate_legacy_attribute_values(self, attribute_values, category):
        seen_attribute_ids = set()
        for value in attribute_values:
            attribute = value["attribute"]
            option = value["option"]
            if attribute.category_id != category.id:
                raise serializers.ValidationError(
                    {
                        "attribute_values": (
                            "Attribute must belong to the selected product category."
                        )
                    }
                )
            if option.attribute_id != attribute.id:
                raise serializers.ValidationError(
                    {
                        "attribute_values": (
                            "Option must belong to the selected attribute."
                        )
                    }
                )
            if attribute.id in seen_attribute_ids:
                raise serializers.ValidationError(
                    {"attribute_values": "Each attribute can be used only once."}
                )
            seen_attribute_ids.add(attribute.id)

    def _validate_attribute_payload(self, attributes):
        names = set()
        for index, attribute in enumerate(attributes, start=1):
            name = attribute.get("name", "").strip()
            if not name:
                raise serializers.ValidationError(
                    {"attributes": f"Attribute {index} name is required."}
                )
            normalized_name = name.casefold()
            if normalized_name in names:
                raise serializers.ValidationError(
                    {"attributes": "Attribute names must be unique per product."}
                )
            names.add(normalized_name)
            option_values = set()
            for option in attribute.get("options", []):
                value = option.get("value", "").strip()
                if not value:
                    raise serializers.ValidationError(
                        {"attributes": f"Option value is required for {name}."}
                    )
                normalized_value = value.casefold()
                if normalized_value in option_values:
                    raise serializers.ValidationError(
                        {"attributes": f"Option values must be unique for {name}."}
                    )
                option_values.add(normalized_value)

    def _validate_variant_payload(self, attributes, variants):
        expected_count = len(attributes or [])
        if expected_count == 0 and len(variants) > 1:
            raise serializers.ValidationError(
                {"variants": "Only one base variant is allowed without attributes."}
            )
        seen_combinations = {}
        expected_attribute_keys = {
            str(attribute.get("client_id") or attribute.get("id"))
            for attribute in attributes or []
        }
        for index, variant in enumerate(variants, start=1):
            selections = self._variant_selections(variant)
            if expected_count and len(selections) != expected_count:
                raise serializers.ValidationError(
                    {"variants": f"Variant {index} is missing attribute selections."}
                )
            if expected_attribute_keys:
                selected_attribute_keys = {
                    str(
                        selection.get("attribute_client_id")
                        or selection.get("attribute_id")
                    )
                    for selection in selections
                }
                if selected_attribute_keys != expected_attribute_keys:
                    raise serializers.ValidationError(
                        {
                            "variants": (
                                f"Variant {index} must select exactly one option "
                                "for every product attribute."
                            )
                        }
                    )
            key = tuple(
                sorted(
                    (
                        str(selection.get("attribute_id") or selection.get("attribute_client_id")),
                        str(selection.get("option_id") or selection.get("option_client_id")),
                    )
                    for selection in selections
                )
            )
            if key in seen_combinations:
                raise serializers.ValidationError(
                    {
                        "variants": (
                            f"Variant {index} duplicates variant "
                            f"{seen_combinations[key]}."
                        )
                    }
                )
            seen_combinations[key] = index

    def _variant_selections(self, variant):
        selections = variant.get("selections")
        if selections is None:
            selections = variant.get("attribute_values", [])
        return selections or []

    @transaction.atomic
    def create(self, validated_data):
        uploads = validated_data.pop("image_uploads", [])
        primary_image_index = validated_data.pop("primary_image_index", None)
        validated_data.pop("image", None)
        attribute_values = validated_data.pop("attribute_values", [])
        attributes = validated_data.pop("attributes", [])
        variants = validated_data.pop("variants", [])
        additions = validated_data.pop("additions", [])
        product = Product.objects.create(**validated_data)
        self._replace_product_attribute_values(product, attribute_values)
        self._replace_attributes(product, attributes)
        self._replace_variants(product, variants)
        product.additions.set(additions)
        if uploads:
            add_product_images(product.id, uploads, primary_image_index)
        from notifications.market_services import (
            schedule_pending_market_notification_for_product,
        )

        schedule_pending_market_notification_for_product(product.id)
        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        uploads = validated_data.pop("image_uploads", [])
        primary_image_index = validated_data.pop("primary_image_index", None)
        legacy_image = validated_data.pop("image", serializers.empty)
        attribute_values = validated_data.pop("attribute_values", None)
        attributes = validated_data.pop("attributes", None)
        variants = validated_data.pop("variants", None)
        additions = validated_data.pop("additions", None)
        instance = super().update(instance, validated_data)
        if attribute_values is not None:
            self._replace_product_attribute_values(instance, attribute_values)
        if attributes is not None:
            self._replace_attributes(instance, attributes)
        if variants is not None:
            self._replace_variants(instance, variants)
        if additions is not None:
            instance.additions.set(additions)
        if uploads:
            add_product_images(instance.id, uploads, primary_image_index)
            instance.refresh_from_db(fields=("image", "updated_at"))
        elif legacy_image is None:
            clear_primary_product_image(instance.id)
            instance.refresh_from_db(fields=("image", "updated_at"))
        from notifications.market_services import (
            schedule_pending_market_notification_for_product,
        )

        schedule_pending_market_notification_for_product(instance.id)
        return instance

    def _replace_product_attribute_values(self, product, attribute_values):
        product.attribute_values.all().delete()
        ProductAttributeValue.objects.bulk_create(
            ProductAttributeValue(product=product, **value)
            for value in attribute_values
        )

    def _replace_variants(self, product, variants):
        product.variants.all().delete()
        attributes_by_id = {attribute.id: attribute for attribute in product.attributes.all()}
        attributes_by_client_id = getattr(self, "_attribute_client_map", {})
        options_by_id = {
            option.id: option
            for option in ProductAttributeOption.objects.filter(
                attribute__product=product
            ).select_related("attribute")
        }
        options_by_client_id = getattr(self, "_option_client_map", {})
        for variant_data in variants:
            selections = self._variant_selections(variant_data)
            variant_data.pop("selections", None)
            variant_data.pop("attribute_values", None)
            variant = ProductVariant.objects.create(
                product=product,
                **variant_data,
            )
            values = []
            for selection in selections:
                legacy_attribute = selection.get("attribute")
                legacy_option = selection.get("option")
                if legacy_attribute is not None and legacy_option is not None:
                    if legacy_option.attribute_id != legacy_attribute.id:
                        raise serializers.ValidationError(
                            {"variants": "Option must belong to the selected attribute."}
                        )
                    values.append(
                        VariantAttributeValue(
                            variant=variant,
                            attribute=legacy_attribute,
                            option=legacy_option,
                        )
                    )
                    continue
                attribute = None
                option = None
                attribute_id = selection.get("attribute_id")
                option_id = selection.get("option_id")
                attribute_client_id = selection.get("attribute_client_id")
                option_client_id = selection.get("option_client_id")
                if attribute_id is not None:
                    attribute = attributes_by_id.get(int(attribute_id))
                elif attribute_client_id is not None:
                    attribute = attributes_by_client_id.get(str(attribute_client_id))
                if option_id is not None:
                    option = options_by_id.get(int(option_id))
                elif option_client_id is not None:
                    option = options_by_client_id.get(str(option_client_id))
                if attribute is None or option is None:
                    raise serializers.ValidationError(
                        {"variants": "Every selection must include valid attribute and option."}
                    )
                if option.attribute_id != attribute.id:
                    raise serializers.ValidationError(
                        {"variants": "Option must belong to the selected attribute."}
                    )
                values.append(
                    VariantAttributeValue(
                        variant=variant,
                        product_attribute=attribute,
                        product_attribute_option=option,
                    )
                )
            VariantAttributeValue.objects.bulk_create(values)

    def _replace_attributes(self, product, attributes):
        product.attributes.all().delete()
        self._attribute_client_map = {}
        self._option_client_map = {}
        for attr_index, attribute_data in enumerate(attributes, start=1):
            options = attribute_data.pop("options", [])
            client_id = attribute_data.pop("client_id", None)
            attribute_data.pop("id", None)
            attribute = ProductAttribute.objects.create(
                product=product,
                sort_order=attribute_data.pop("sort_order", attr_index - 1),
                **attribute_data,
            )
            if client_id:
                self._attribute_client_map[str(client_id)] = attribute
            for option_index, option_data in enumerate(options, start=1):
                option_client_id = option_data.pop("client_id", None)
                option_data.pop("id", None)
                option = ProductAttributeOption.objects.create(
                    attribute=attribute,
                    sort_order=option_data.pop("sort_order", option_index - 1),
                    **option_data,
                )
                if option_client_id:
                    self._option_client_map[str(option_client_id)] = option

