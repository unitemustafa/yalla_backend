from rest_framework import serializers


CREATE_SYSTEM_CONTROLLED_FIELDS = {
    "client_request_key",
    "client_request_hash",
    "assigned_representative_id",
    "assigned_at",
    "delivered_at",
    "delivery_area_id",
    "delivery_type",
    "delivery_price",
    "order_scope",
    "discount",
    "subtotal_price",
    "total_price",
    "image",
    "delivery_proof",
    "market_sections",
    "status",
    "review_status",
    "approved_by",
    "approved_at",
    "rejected_by",
    "rejected_at",
    "rejection_reason",
}


def normalized_order_request_data(data, *, include_create_fields=False):
    """Copy only checkout fields that clients are allowed to control."""

    if include_create_fields:
        errors = {
            field: "This field is controlled by the system on create."
            for field in sorted(CREATE_SYSTEM_CONTROLLED_FIELDS)
            if field in data
        }
        if errors:
            raise serializers.ValidationError(errors)

    if not hasattr(data, "get"):
        raise serializers.ValidationError({"detail": "Expected an object."})
    for field in ("items", "offers"):
        rows = data.get(field, [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise serializers.ValidationError({field: "Expected a list of objects."})

    addition_ids_field = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=True,
    )

    def addition_fields(item):
        if "addition_ids" not in item:
            return {}
        try:
            return {
                "addition_ids": sorted(
                    addition_ids_field.run_validation(item["addition_ids"])
                )
            }
        except serializers.ValidationError as error:
            raise serializers.ValidationError({"addition_ids": error.detail}) from error

    normalized = {
        "items": [
            {
                "variant_id": item.get("variant_id"),
                "quantity": item.get("quantity"),
                **addition_fields(item),
            }
            for item in data.get("items", [])
        ],
        "offers": [
            {"offer_id": item.get("offer_id")} for item in data.get("offers", [])
        ],
    }

    if "market_order" in data:
        normalized["market_order"] = data.get("market_order")

    address_id = data.get("address_id", data.get("delivery_address_id"))
    service_city_id = data.get("service_city_id")
    if address_id not in (None, ""):
        normalized["address_id"] = address_id
    if service_city_id not in (None, ""):
        normalized["service_city_id"] = service_city_id

    if include_create_fields:
        for field in (
            "payment_method",
            "description",
            "delivery_note",
            "shipping_company_id",
        ):
            value = data.get(field)
            if value not in (None, ""):
                normalized[field] = value

    return normalized
