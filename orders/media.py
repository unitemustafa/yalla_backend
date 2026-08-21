from django.urls import reverse


def protected_order_media_url(request, order, kind):
    field = getattr(order, kind)
    if not field:
        return None

    version = "v2" if request and request.path_info.startswith("/api/v2/") else "v1"
    route_name = "order-image" if kind == "image" else "order-delivery-proof"
    if version == "v2":
        path = reverse(
            f"v2:{route_name}",
            kwargs={"order_id": order.pk},
        )
    else:
        path = reverse(route_name, kwargs={"order_id": order.pk})
    return request.build_absolute_uri(path) if request else path
