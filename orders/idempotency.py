import hashlib
import json
import re

from rest_framework.exceptions import APIException, ValidationError

from .models import Order


class OrderRequestConflict(APIException):
    status_code = 409
    default_detail = "This order request key was already used for different checkout details."
    default_code = "order_request_conflict"


def order_request_identity(request, data):
    key = request.headers.get("Idempotency-Key")
    if key is None:
        # Older clients can continue using the existing endpoint.
        return None, ""
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", key):
        raise ValidationError({"detail": "Invalid Idempotency-Key header."})
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return key, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def existing_order_for_request(user, key, fingerprint):
    if key is None:
        return None
    # The caller holds the user's row lock until the transaction commits.
    order = Order.objects.filter(user=user, client_request_key=key).first()
    if order is not None and order.client_request_hash != fingerprint:
        raise OrderRequestConflict()
    return order
