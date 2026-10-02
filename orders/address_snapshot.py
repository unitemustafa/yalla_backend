"""JSON-safe delivery instructions retained independently of the address book."""


def address_snapshot(address):
    if address is None:
        return {}
    fields = (
        "id",
        "name",
        "label",
        "details",
        "formatted_address",
        "address_type",
        "recipient_name",
        "recipient_phone",
        "street",
        "building_name",
        "apartment_number",
        "floor",
        "company_name",
        "additional_instructions",
        "governorate",
        "district",
        "manual_city",
        "manual_area",
        "delivery_type",
        "fulfillment_type",
    )
    snapshot = {field: getattr(address, field) for field in fields}
    snapshot.update(
        latitude=float(address.latitude) if address.latitude is not None else None,
        longitude=float(address.longitude) if address.longitude is not None else None,
    )
    for relation in ("service_city", "delivery_area"):
        related = getattr(address, relation)
        snapshot[relation] = (
            None
            if related is None
            else {
                "id": related.id,
                "name": related.name,
                "delivery_price": f"{related.delivery_price:.2f}",
                "is_active": related.is_active,
                **(
                    {"service_city_id": related.service_city_id}
                    if relation == "delivery_area"
                    else {}
                ),
            }
        )
    snapshot["delivery_price_preview"] = (
        f"{address.delivery_area.delivery_price:.2f}"
        if address.delivery_type == "fixed_area" and address.delivery_area_id
        else None
    )
    return snapshot
