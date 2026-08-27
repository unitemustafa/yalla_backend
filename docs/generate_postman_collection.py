#!/usr/bin/env python3
"""Generate the maintained Yalla Postman collection from the OpenAPI contract.

The OpenAPI file is the endpoint inventory. Request examples, role-specific
tokens, workflow scripts, and legacy APIView payloads are maintained here
because the current schema intentionally exposes some of those payloads as
undocumented placeholders.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "openapi.yml"
OUTPUT_PATH = ROOT / "docs" / "Yalla System APIs.postman_collection.json"
API_SCHEMA_PREFIX = "/api/v2"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def raw(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": "raw",
        "raw": json.dumps(payload, ensure_ascii=False, indent=2),
        "options": {"raw": {"language": "json"}},
    }


def form(*fields: tuple[str, str, str, bool]) -> dict[str, Any]:
    values = []
    for key, value, field_type, disabled in fields:
        item: dict[str, Any] = {
            "key": key,
            "type": field_type,
            "disabled": disabled,
        }
        if field_type == "file":
            item["src"] = value
        else:
            item["value"] = value
        values.append(item)
    return {"mode": "formdata", "formdata": values}


ADDRESS_CREATE = {
    "service_city_id": "{{service_city_id}}",
    "delivery_area_id": "{{delivery_area_id}}",
    "delivery_type": "fixed_area",
    "name": "Home",
    "address_type": "apartment",
    "recipient_name": "Postman Customer",
    "recipient_phone": "+201012345678",
    "building_name": "Building 10",
    "apartment_number": "12",
    "floor": "3",
    "additional_instructions": "Call on arrival",
    "line1": "10 Example Street",
    "city": "Cairo",
    "state": "Cairo",
    "country": "Egypt",
    "postal_code": "11511",
    "formatted_address": "10 Example Street, Cairo, Egypt",
    "latitude": "30.0444196",
    "longitude": "31.2357116",
    "is_default": True,
}

PRODUCT_CREATE = {
    "market_id": "{{market_id}}",
    "category_id": "{{product_category_id}}",
    "subcategory_id": "{{store_subcategory_id}}",
    "theme": "consumer",
    "is_popular": False,
    "is_available": True,
    "name": "Postman Product {{run_suffix}}",
    "description": "Product created from the maintained Postman collection.",
    "discount": "0.00",
    "attributes": [
        {
            "client_id": "size",
            "name": "Size",
            "sort_order": 0,
            "options": [
                {
                    "client_id": "medium",
                    "value": "Medium",
                    "sort_order": 0,
                }
            ],
        }
    ],
    "variants": [
        {
            "price": "49.90",
            "sku": "POSTMAN-{{run_suffix}}",
            "selections": [
                {
                    "attribute_client_id": "size",
                    "option_client_id": "medium",
                }
            ],
        }
    ],
    "additions": [],
}

OFFER_CREATE = {
    "market_id": "{{market_id}}",
    "show_in_general": False,
    "service_city_ids": ["{{service_city_id}}"],
    "product_ids": ["{{product_id}}"],
    "items": [
        {
            "variant_id": "{{variant_id}}",
            "quantity": 1,
            "apply_product_discount": True,
        }
    ],
    "title": "Postman Offer {{run_suffix}}",
    "description": "Offer created from Postman.",
    "type": "discount",
    "discount": "5.00",
    "start_time": "{{offer_start_time}}",
    "end_time": "{{offer_end_time}}",
    "active_days": [0, 1, 2, 3, 4, 5, 6],
    "use_limits": 100,
    "user_limit": 1,
    "status": "active",
    "send_push_notification": False,
}

ORDER_PREVIEW = {
    "address_id": "{{address_id}}",
    "items": [{"variant_id": "{{variant_id}}", "quantity": 2}],
    "offers": [],
}

ORDER_CREATE = {
    **ORDER_PREVIEW,
    "shipping_company_id": "{{shipping_company_id}}",
    "payment_method": "cash",
    "description": "Order created from Postman.",
    "delivery_note": "Please call before delivery.",
}


BODY_EXAMPLES: dict[tuple[str, str], dict[str, Any]] = {
    ("POST", "/addresses/"): raw(ADDRESS_CREATE),
    ("PATCH", "/addresses/{address_id}/"): raw(
        {"name": "Updated Home", "additional_instructions": "Ring twice"}
    ),
    ("POST", "/admin/orders/{order_id}/approve/"): raw({}),
    ("POST", "/admin/orders/{order_id}/reject/"): raw(
        {"rejection_reason": "The order requires customer clarification."}
    ),
    ("PUT", "/auth/client/profile/"): raw(
        {
            "first_name": "Postman",
            "last_name": "Customer",
            "gender": "",
            "birth_date": None,
            "avatar_url": "https://example.com/avatar.png",
        }
    ),
    ("PATCH", "/auth/client/profile/"): form(
        ("first_name", "Postman", "text", False),
        ("last_name", "Customer", "text", False),
        ("avatar", "{{sample_image_path}}", "file", True),
        ("remove_avatar", "false", "text", True),
    ),
    ("DELETE", "/auth/client/profile/"): raw(
        {"password": "{{client_password}}"}
    ),
    ("POST", "/auth/forgot-password/"): raw(
        {"email": "{{client_email}}"}
    ),
    ("POST", "/auth/login/"): raw(
        {"identifier": "{{client_email}}", "password": "{{client_password}}"}
    ),
    ("POST", "/auth/login/admin/"): raw(
        {
            "identifier": "{{admin_email}}",
            "password": "{{admin_password}}",
            "remember": False,
        }
    ),
    ("POST", "/auth/login/client/"): raw(
        {
            "identifier": "{{client_email}}",
            "password": "{{client_password}}",
            "remember": False,
        }
    ),
    ("POST", "/auth/login/representative/"): raw(
        {
            "identifier": "{{representative_email}}",
            "password": "{{representative_password}}",
            "remember": False,
        }
    ),
    ("POST", "/auth/logout/"): raw({"refreshToken": "{{refresh_token}}"}),
    ("PATCH", "/auth/me/"): raw(
        {"first_name": "Postman", "last_name": "Customer"}
    ),
    ("POST", "/auth/refresh/"): raw({"refreshToken": "{{refresh_token}}"}),
    ("POST", "/auth/resend-verification/"): raw(
        {"email": "{{signup_email}}"}
    ),
    ("POST", "/auth/reset-password/"): raw(
        {
            "email": "{{client_email}}",
            "otp": "{{reset_otp}}",
            "password": "{{new_password}}",
            "password_confirm": "{{new_password}}",
        }
    ),
    ("POST", "/auth/signup/"): raw(
        {
            "first_name": "Postman",
            "last_name": "Customer",
            "username": "{{signup_username}}",
            "email": "{{signup_email}}",
            "phone": "{{signup_phone}}",
            "password": "{{signup_password}}",
            "password_confirm": "{{signup_password}}",
            "terms_accepted": True,
        }
    ),
    ("POST", "/auth/users/"): raw(
        {
            "first_name": "Postman",
            "last_name": "Representative",
            "username": "{{new_user_username}}",
            "email": "{{new_user_email}}",
            "phone": "{{new_user_phone}}",
            "password": "{{new_user_password}}",
            "gender": "",
            "birth_date": None,
            "role": "representative",
            "is_active": True,
            "courier_profile": {
                "vehicle_type": "motorcycle",
                "plate_number": "PM-{{run_suffix}}",
                "service_city": "{{service_city_id}}",
                "delivery_area": "{{delivery_area_id}}",
                "max_active_orders": 3,
                "is_available": True,
            },
        }
    ),
    ("PATCH", "/auth/users/{user_id}/"): raw(
        {"first_name": "Updated", "is_active": True}
    ),
    ("POST", "/auth/verify-email/"): raw(
        {"email": "{{signup_email}}", "otp": "{{registration_otp}}"}
    ),
    ("POST", "/catalog/addition-classifications/"): raw(
        {"name": "Postman Additions {{run_suffix}}"}
    ),
    ("PATCH", "/catalog/addition-classifications/{classification_id}/"): raw(
        {"name": "Updated Addition Classification"}
    ),
    ("POST", "/catalog/category-attributes/"): raw(
        {"category_id": "{{product_category_id}}", "name": "Color"}
    ),
    ("PATCH", "/catalog/category-attributes/{attribute_id}/"): raw(
        {"name": "Updated Color"}
    ),
    ("POST", "/catalog/category-classifications/"): raw(
        {"name": "Postman Categories {{run_suffix}}"}
    ),
    ("PATCH", "/catalog/category-classifications/{classification_id}/"): raw(
        {"name": "Updated Category Classification"}
    ),
    ("POST", "/catalog/category-options/"): raw(
        {"attribute_id": "{{attribute_id}}", "value": "Blue"}
    ),
    ("PATCH", "/catalog/category-options/{option_id}/"): raw(
        {"value": "Navy Blue"}
    ),
    ("POST", "/catalog/product-additions/"): form(
        (
            "classification_id",
            "{{addition_classification_id}}",
            "text",
            False,
        ),
        ("name_ar", "إضافة بوستمان", "text", False),
        ("name_en", "Postman addition", "text", False),
        ("price", "10.00", "text", False),
        ("is_active", "true", "text", False),
        ("image", "{{sample_image_path}}", "file", True),
    ),
    ("PATCH", "/catalog/product-additions/{addition_id}/"): raw(
        {"name_en": "Updated Postman addition", "price": "12.00"}
    ),
    ("POST", "/catalog/product-categories/"): form(
        (
            "classification_id",
            "{{category_classification_id}}",
            "text",
            False,
        ),
        ("name", "Postman Category {{run_suffix}}", "text", False),
        ("type", "other", "text", False),
        ("description", "Created from Postman", "text", False),
        ("image", "{{sample_image_path}}", "file", True),
    ),
    ("PATCH", "/catalog/product-categories/{category_id}/"): raw(
        {"name": "Updated Postman Category"}
    ),
    ("POST", "/catalog/products/"): raw(PRODUCT_CREATE),
    ("PUT", "/catalog/products/{product_id}/"): raw(PRODUCT_CREATE),
    ("PATCH", "/catalog/products/{product_id}/"): raw(
        {"name": "Updated Postman Product", "is_popular": True}
    ),
    ("POST", "/catalog/products/{product_id}/images/"): form(
        ("images", "{{sample_image_path}}", "file", False),
        ("images", "{{second_image_path}}", "file", True),
        ("primary_image_index", "0", "text", False),
    ),
    (
        "PATCH",
        "/catalog/products/{product_id}/images/{image_id}/",
    ): raw({"is_primary": True}),
    ("POST", "/catalog/products/{product_id}/images/reorder/"): raw(
        {"image_ids": ["{{image_id}}"]}
    ),
    ("POST", "/catalog/products/{product_id}/send-notification/"): raw(
        {"request_id": "{{$guid}}"}
    ),
    ("POST", "/catalog/store-subcategories/"): form(
        ("name_ar", "قسم بوستمان", "text", False),
        ("name_en", "Postman section {{run_suffix}}", "text", False),
        ("description_ar", "تم إنشاؤه من بوستمان", "text", False),
        ("description_en", "Created from Postman", "text", False),
        ("is_active", "true", "text", False),
        ("image", "{{sample_image_path}}", "file", True),
    ),
    ("PATCH", "/catalog/store-subcategories/{subcategory_id}/"): raw(
        {"name_en": "Updated Postman section"}
    ),
    ("PATCH", "/courier/orders/{order_id}/status/"): form(
        ("status", "delivered", "text", False),
        ("delivery_note", "Delivered to the customer", "text", False),
        ("delivery_proof", "{{sample_image_path}}", "file", False),
    ),
    ("PATCH", "/dashboard/settings/"): form(
        ("primary_color", "#0057B8", "text", False),
        ("subtle_color", "#EAF2FF", "text", False),
        ("accent_color", "#FFB703", "text", False),
        ("font_family", "Cairo", "text", False),
        ("brand_name", "Yalla", "text", False),
        ("brand_tagline", "Everything delivered", "text", False),
        ("logo", "{{sample_image_path}}", "file", True),
        ("remove_logo", "false", "text", True),
    ),
    ("POST", "/home/market-classifications/"): form(
        ("name", "Postman Markets {{run_suffix}}", "text", False),
        ("description", "Created from Postman", "text", False),
        ("classification_type", "normal", "text", False),
        ("is_active", "true", "text", False),
        ("image", "{{sample_image_path}}", "file", True),
    ),
    ("PATCH", "/home/market-classifications/{classification_id}/"): raw(
        {"name": "Updated Market Classification", "is_active": True}
    ),
    ("POST", "/home/market-types/"): form(
        (
            "classification_id",
            "{{market_classification_id}}",
            "text",
            False,
        ),
        ("name_ar", "نوع بوستمان", "text", False),
        ("name_en", "Postman type {{run_suffix}}", "text", False),
        ("sort_order", "10", "text", False),
        ("is_active", "true", "text", False),
        ("image", "{{sample_image_path}}", "file", False),
    ),
    ("PATCH", "/home/market-types/{market_type_id}/"): form(
        ("name_en", "Updated Postman type", "text", False),
        ("sort_order", "20", "text", False),
        ("image", "{{sample_image_path}}", "file", True),
    ),
    ("POST", "/home/markets/"): form(
        (
            "classification_id",
            "{{market_classification_id}}",
            "text",
            False,
        ),
        ("name", "Postman Market {{run_suffix}}", "text", False),
        ("description", "Created from Postman", "text", False),
        ("branch", "Main branch", "text", False),
        ("scope", "service_city", "text", False),
        ("status", "active", "text", False),
        ("delivery_time_min_minutes", "20", "text", False),
        ("delivery_time_max_minutes", "45", "text", False),
        ("is_popular", "false", "text", False),
        ("service_city_ids", "{{service_city_id}}", "text", False),
        ("delivery_area_ids", "{{delivery_area_id}}", "text", False),
        ("subcategory_ids", "{{store_subcategory_id}}", "text", False),
        ("market_type_ids", "{{market_type_id}}", "text", False),
        ("send_notification", "false", "text", False),
        ("image", "{{sample_image_path}}", "file", False),
        ("cover_image", "{{sample_image_path}}", "file", False),
    ),
    ("PATCH", "/home/markets/{market_id}/"): raw(
        {"description": "Updated from Postman", "is_popular": True}
    ),
    ("POST", "/locations/addresses/"): raw(ADDRESS_CREATE),
    ("PATCH", "/locations/addresses/{address_id}/"): raw(
        {"name": "Updated Home", "additional_instructions": "Ring twice"}
    ),
    ("POST", "/locations/delivery-areas/"): raw(
        {
            "service_city_id": "{{service_city_id}}",
            "name": "Postman Area {{run_suffix}}",
            "center_latitude": "30.0444196",
            "center_longitude": "31.2357116",
            "radius_km": "5.00",
            "delivery_price": "35.00",
            "eta_min_minutes": 20,
            "eta_max_minutes": 45,
            "is_active": True,
        }
    ),
    ("PUT", "/locations/delivery-areas/{area_id}/"): raw(
        {
            "service_city_id": "{{service_city_id}}",
            "name": "Replaced Postman Area",
            "center_latitude": "30.0444196",
            "center_longitude": "31.2357116",
            "radius_km": "6.00",
            "delivery_price": "40.00",
            "eta_min_minutes": 20,
            "eta_max_minutes": 50,
            "is_active": True,
        }
    ),
    ("PATCH", "/locations/delivery-areas/{area_id}/"): raw(
        {"delivery_price": "40.00", "eta_max_minutes": 50}
    ),
    ("POST", "/locations/shipping-companies/"): form(
        ("name", "Postman Shipping {{run_suffix}}", "text", False),
        ("service_city_ids", "{{service_city_id}}", "text", False),
        ("is_active", "true", "text", False),
        ("logo", "{{sample_image_path}}", "file", True),
    ),
    ("PUT", "/locations/shipping-companies/{company_id}/"): form(
        ("name", "Replaced Postman Shipping", "text", False),
        ("service_city_ids", "{{service_city_id}}", "text", False),
        ("is_active", "true", "text", False),
        ("logo", "{{sample_image_path}}", "file", True),
    ),
    ("PATCH", "/locations/shipping-companies/{company_id}/"): raw(
        {"is_active": False}
    ),
    ("POST", "/locations/service-cities/"): raw(
        {
            "name": "Postman City {{run_suffix}}",
            "center_latitude": "30.0444196",
            "center_longitude": "31.2357116",
            "radius_km": "20.00",
            "delivery_price": "35.00",
            "is_active": True,
        }
    ),
    ("PUT", "/locations/service-cities/{city_id}/"): raw(
        {
            "name": "Replaced Postman City",
            "center_latitude": "30.0444196",
            "center_longitude": "31.2357116",
            "radius_km": "25.00",
            "delivery_price": "40.00",
            "is_active": True,
        }
    ),
    ("PATCH", "/locations/service-cities/{city_id}/"): raw(
        {"delivery_price": "40.00"}
    ),
    ("POST", "/market-region/detect/"): raw(
        {"latitude": "30.0444196", "longitude": "31.2357116"}
    ),
    ("PATCH", "/market-region/me/"): raw(
        {"mode": "service_city", "service_city_id": "{{service_city_id}}"}
    ),
    ("POST", "/notifications/devices/register/"): raw(
        {"token": "{{fcm_device_token}}", "platform": "android"}
    ),
    ("DELETE", "/notifications/devices/unregister/"): raw(
        {"token": "{{fcm_device_token}}", "platform": "android"}
    ),
    ("POST", "/offers/"): raw(OFFER_CREATE),
    ("PATCH", "/offers/{offer_id}/"): raw(
        {"title": "Updated Postman Offer", "status": "active"}
    ),
    ("POST", "/offers/{offer_id}/image/"): form(
        ("image", "{{sample_image_path}}", "file", False),
    ),
    ("POST", "/offers/{offer_id}/send-notification/"): raw(
        {"request_id": "{{$guid}}"}
    ),
    ("POST", "/orders/"): raw(
        {
            "user_id": "{{client_user_id}}",
            "delivery_address_id": "{{address_id}}",
            "payment_method": "cash",
            "description": "Admin-created Postman order.",
            "delivery_note": "Call before delivery.",
            "items": [{"variant_id": "{{variant_id}}", "quantity": 1}],
            "offers": [],
        }
    ),
    ("PUT", "/orders/{order_id}/"): raw(
        {
            "user_id": "{{client_user_id}}",
            "delivery_address_id": "{{address_id}}",
            "payment_method": "cash",
            "description": "Replaced admin order.",
            "delivery_note": "Call before delivery.",
            "items": [{"variant_id": "{{variant_id}}", "quantity": 1}],
            "offers": [],
        }
    ),
    ("PATCH", "/orders/{order_id}/"): raw(
        {"description": "Updated by Postman", "delivery_note": "Updated note"}
    ),
    ("PATCH", "/orders/{order_id}/assignment/"): raw(
        {"representative_id": "{{representative_id}}"}
    ),
    ("PATCH", "/orders/{order_id}/delivery-price/"): raw(
        {"delivery_price": "45.00", "action": "request_approval"}
    ),
    ("POST", "/orders/{order_id}/delivery-price/accept/"): raw({}),
    ("PATCH", "/orders/{order_id}/status/"): raw({"status": "confirmed"}),
    ("POST", "/orders/create/"): raw(ORDER_CREATE),
    ("POST", "/orders/preview/"): raw(ORDER_PREVIEW),
    ("PATCH", "/partners/admin/applications/{application_id}/"): raw(
        {"status": "in_review", "admin_notes": "Reviewed from Postman."}
    ),
    ("POST", "/partners/applications/"): raw(
        {
            "business_name": "Postman Business {{run_suffix}}",
            "contact_first_name": "Postman",
            "contact_last_name": "Owner",
            "business_type": "shop",
            "branches_count": 1,
            "applicant_role": "owner_partner",
            "has_trade_license": True,
            "email": "partner+{{run_suffix}}@example.com",
            "mobile_number": "+201012345678",
            "landline": "",
            "whatsapp_opt_in": True,
            "notes": "Application created from Postman.",
        }
    ),
}


EMPTY_BODY_OPERATIONS = {
    ("PATCH", "/addresses/{address_id}/default/"),
    ("POST", "/catalog/products/{product_id}/like/"),
    ("POST", "/home/markets/{market_id}/like/"),
    ("PATCH", "/locations/addresses/{address_id}/default/"),
    ("PATCH", "/notifications/{notification_id}/read/"),
    ("POST", "/notifications/mark-all-read/"),
}


QUERY_EXAMPLES: dict[tuple[str, str], list[dict[str, Any]]] = {
    ("GET", "/auth/check-email/"): [
        {"key": "email", "value": "{{client_email}}"},
        {"key": "exclude_user_id", "value": "{{user_id}}", "disabled": True},
    ],
    ("GET", "/auth/check-phone/"): [
        {"key": "phone", "value": "+201012345678"},
        {"key": "exclude_user_id", "value": "{{user_id}}", "disabled": True},
    ],
    ("GET", "/auth/check-username/"): [
        {"key": "username", "value": "{{signup_username}}"},
        {"key": "exclude_user_id", "value": "{{user_id}}", "disabled": True},
    ],
    ("GET", "/catalog/store-subcategories/"): [
        {"key": "is_active", "value": "true"}
    ],
    ("GET", "/catalog/products/"): [
        {"key": "archived", "value": "false"}
    ],
    ("GET", "/home/market-types/"): [
        {"key": "classification_id", "value": "{{market_classification_id}}"}
    ],
    ("GET", "/home/markets/"): [{"key": "archived", "value": "false"}],
    ("GET", "/home/products/"): [
        {"key": "order_by_latest", "value": "true"},
        {"key": "order_by_name", "value": "true", "disabled": True},
        {"key": "order_by_high_price", "value": "true", "disabled": True},
        {"key": "order_by_low_price", "value": "true", "disabled": True},
    ],
    ("GET", "/home/search/"): [{"key": "q", "value": "milk"}],
    ("GET", "/locations/addresses/"): [
        {"key": "user_id", "value": "{{client_user_id}}", "disabled": True}
    ],
    ("GET", "/locations/delivery-areas/"): [
        {"key": "service_city_id", "value": "{{service_city_id}}"},
        {"key": "archived", "value": "false", "disabled": True},
    ],
    ("GET", "/locations/geocoding/autocomplete/"): [
        {"key": "q", "value": "Nasr City"},
        {"key": "latitude", "value": "30.0444196"},
        {"key": "longitude", "value": "31.2357116"},
        {"key": "lang", "value": "en"},
    ],
    ("GET", "/locations/geocoding/reverse/"): [
        {"key": "latitude", "value": "30.0444196"},
        {"key": "longitude", "value": "31.2357116"},
        {"key": "lang", "value": "en"},
    ],
    ("GET", "/locations/service-cities/"): [
        {"key": "archived", "value": "false"}
    ],
    ("GET", "/locations/shipping-companies/"): [
        {"key": "service_city_id", "value": "{{service_city_id}}"},
        {"key": "archived", "value": "false", "disabled": True},
    ],
    ("GET", "/locations/service-cities/coverage-lookup/"): [
        {"key": "q", "value": "Cairo"},
        {"key": "lang", "value": "en"},
    ],
    ("GET", "/notifications/"): [
        {"key": "unread", "value": "true"},
        {"key": "type", "value": "", "disabled": True},
        {"key": "audience", "value": "client", "disabled": True},
        {"key": "is_blocking", "value": "false", "disabled": True},
        {"key": "is_resolved", "value": "false", "disabled": True},
    ],
    ("GET", "/offers/"): [{"key": "archived", "value": "false"}],
    ("GET", "/orders/"): [
        {"key": "status", "value": "pending", "disabled": True}
    ],
    ("GET", "/orders/my/"): [
        {"key": "status", "value": "pending", "disabled": True}
    ],
    ("GET", "/courier/orders/"): [
        {"key": "status", "value": "assigned", "disabled": True}
    ],
    ("GET", "/partners/admin/applications/"): [
        {"key": "status", "value": "pending"},
        {"key": "search", "value": "Postman", "disabled": True},
    ],
    ("GET", "/dashboard/overview/"): [
        {"key": "from", "value": "{{dashboard_from}}"},
        {"key": "to", "value": "{{dashboard_to}}"},
    ],
}


PUBLIC_API_PATHS = {
    "/auth/check-email/",
    "/auth/check-phone/",
    "/auth/check-username/",
    "/auth/forgot-password/",
    "/auth/login/",
    "/auth/login/admin/",
    "/auth/login/client/",
    "/auth/login/representative/",
    "/auth/refresh/",
    "/auth/resend-verification/",
    "/auth/reset-password/",
    "/auth/signup/",
    "/auth/verify-email/",
    "/home/login-dashboard-snapshot/",
}


NAME_OVERRIDES = {
    ("POST", "/auth/signup/"): "POST · Sign up and send registration OTP",
    ("POST", "/auth/verify-email/"): "POST · Verify registration OTP",
    ("POST", "/auth/resend-verification/"): "POST · Resend registration OTP",
    ("POST", "/auth/login/"): "POST · Generic login",
    ("POST", "/auth/login/client/"): "POST · Client login",
    ("POST", "/auth/login/representative/"): "POST · Representative login",
    ("POST", "/auth/login/admin/"): "POST · Admin login",
    ("POST", "/auth/refresh/"): "POST · Rotate refresh token",
    ("POST", "/auth/logout/"): "POST · Logout and revoke refresh token",
    ("GET", "/auth/me/"): "GET · Current user",
    ("PATCH", "/auth/me/"): "PATCH · Current user profile",
    ("POST", "/auth/forgot-password/"): "POST · Send password reset OTP",
    ("POST", "/auth/reset-password/"): "POST · Reset password with OTP",
    ("GET", "/home/"): "GET · Home feed",
    ("GET", "/home/login-dashboard-snapshot/"): "GET · Public login snapshot",
    ("POST", "/orders/preview/"): "POST · Preview client order",
    ("POST", "/orders/create/"): "POST · Create client order",
    ("GET", "/orders/my/"): "GET · My client orders",
}


COLLECTION_VARIABLES = [
    ("base_url", "http://127.0.0.1:8000", "string"),
    ("api_version", "v2", "string"),
    ("api_base", "{{base_url}}/api/{{api_version}}", "string"),
    ("allow_destructive_requests", "false", "string"),
    ("allow_account_deletion", "false", "string"),
    ("run_suffix", "", "string"),
    ("admin_email", "seed.admin@yalla.seed", "string"),
    ("admin_password", "SeedPass1!", "string"),
    ("client_email", "seed.amina@yalla.seed", "string"),
    ("client_password", "SeedPass1!", "string"),
    ("representative_email", "seed.courier1@yalla.seed", "string"),
    ("representative_password", "SeedPass1!", "string"),
    ("signup_email", "", "string"),
    ("signup_username", "", "string"),
    ("signup_phone", "", "string"),
    ("signup_password", "PostmanPass1!", "string"),
    ("registration_otp", "", "string"),
    ("reset_otp", "", "string"),
    ("new_password", "PostmanNewPass2!", "string"),
    ("new_user_email", "", "string"),
    ("new_user_username", "", "string"),
    ("new_user_phone", "", "string"),
    ("new_user_password", "PostmanUser1!", "string"),
    ("access_token", "", "string"),
    ("refresh_token", "", "string"),
    ("admin_access_token", "", "string"),
    ("admin_refresh_token", "", "string"),
    ("client_access_token", "", "string"),
    ("client_refresh_token", "", "string"),
    ("representative_access_token", "", "string"),
    ("representative_refresh_token", "", "string"),
    ("client_user_id", "", "string"),
    ("user_id", "", "string"),
    ("representative_id", "", "string"),
    ("service_city_id", "", "string"),
    ("delivery_area_id", "", "string"),
    ("address_id", "", "string"),
    ("market_classification_id", "", "string"),
    ("market_type_id", "", "string"),
    ("market_id", "", "string"),
    ("store_subcategory_id", "", "string"),
    ("addition_classification_id", "", "string"),
    ("category_classification_id", "", "string"),
    ("product_category_id", "", "string"),
    ("attribute_id", "", "string"),
    ("option_id", "", "string"),
    ("addition_id", "", "string"),
    ("product_id", "", "string"),
    ("variant_id", "", "string"),
    ("image_id", "", "string"),
    ("offer_id", "", "string"),
    ("order_id", "", "string"),
    ("notification_id", "", "string"),
    ("partner_application_id", "", "string"),
    ("fcm_device_token", "replace-with-real-fcm-token", "string"),
    ("sample_image_path", "", "string"),
    ("second_image_path", "", "string"),
    ("offer_start_time", "", "string"),
    ("offer_end_time", "", "string"),
    ("dashboard_from", "", "string"),
    ("dashboard_to", "", "string"),
]


FOLDER_ORDER = {
    "00 System & Public": 0,
    "01 Authentication": 1,
    "02 Admin Users": 2,
    "03 Region & Locations": 3,
    "04 Storefront": 4,
    "05 Markets Admin": 5,
    "06 Catalog Admin": 6,
    "07 Offers": 7,
    "08 Orders - Client": 8,
    "09 Orders - Admin": 9,
    "10 Courier": 10,
    "11 Notifications": 11,
    "12 Partners": 12,
    "13 Dashboard": 13,
}

FOLDER_DESCRIPTIONS = {
    "00 System & Public": (
        "مسارات الصحة والجاهزية والصفحات العامة وواجهات توثيق OpenAPI."
    ),
    "01 Authentication": (
        "التسجيل وOTP وتسجيل الدخول وتجديد التوكن والملف الشخصي. "
        "طلبات الدخول تحفظ التوكنات تلقائياً في Collection Variables."
    ),
    "02 Admin Users": "إدارة المستخدمين والطيارين. يتطلب Admin JWT.",
    "03 Region & Locations": (
        "اختيار المنطقة، المدن، مناطق التوصيل، العناوين وGeoapify."
    ),
    "04 Storefront": "واجهات تطبيق العميل للـ home والبحث والأسواق والمنتجات.",
    "05 Markets Admin": "إدارة تصنيفات وأنواع ومحلات السوق.",
    "06 Catalog Admin": "إدارة الكتالوج والمنتجات والصور والإضافات.",
    "07 Offers": "قراءة العروض للعميل وإدارتها وإرسال إشعاراتها كمدير.",
    "08 Orders - Client": "معاينة وإنشاء ومتابعة طلبات العميل.",
    "09 Orders - Admin": "إدارة الطلبات والمراجعة والتسعير والإسناد.",
    "10 Courier": "قائمة طلبات الطيار وتفاصيلها وتحديث دورة التوصيل.",
    "11 Notifications": "صندوق الإشعارات وإدارة FCM device token.",
    "12 Partners": "طلبات الشراكة ومراجعتها من لوحة الإدارة.",
    "13 Dashboard": "ملخص وإعدادات لوحة الإدارة.",
}

PAGINATED_PATHS = {
    "/addresses/",
    "/auth/representatives/",
    "/auth/users/",
    "/catalog/addition-classifications/",
    "/catalog/category-attributes/",
    "/catalog/category-classifications/",
    "/catalog/category-options/",
    "/catalog/product-additions/",
    "/catalog/product-categories/",
    "/catalog/products/",
    "/catalog/products/likes/",
    "/catalog/store-subcategories/",
    "/courier/orders/",
    "/home/market-classifications/",
    "/home/market-types/",
    "/home/markets/",
    "/home/markets/likes/",
    "/home/products/",
    "/locations/addresses/",
    "/locations/delivery-areas/",
    "/locations/service-cities/",
    "/locations/shipping-companies/",
    "/notifications/",
    "/offers/",
    "/orders/",
    "/orders/my/",
    "/partners/admin/applications/",
    "/partners/applications/",
}

CAPTURE_IDS = {
    "/auth/representatives/": "representative_id",
    "/auth/users/": "user_id",
    "/catalog/addition-classifications/": "addition_classification_id",
    "/catalog/category-attributes/": "attribute_id",
    "/catalog/category-classifications/": "category_classification_id",
    "/catalog/category-options/": "option_id",
    "/catalog/product-additions/": "addition_id",
    "/catalog/product-categories/": "product_category_id",
    "/catalog/products/": "product_id",
    "/catalog/store-subcategories/": "store_subcategory_id",
    "/home/market-classifications/": "market_classification_id",
    "/home/market-types/": "market_type_id",
    "/home/markets/": "market_id",
    "/home/products/": "product_id",
    "/locations/addresses/": "address_id",
    "/addresses/": "address_id",
    "/locations/delivery-areas/": "delivery_area_id",
    "/locations/service-cities/": "service_city_id",
    "/locations/shipping-companies/": "shipping_company_id",
    "/notifications/": "notification_id",
    "/offers/": "offer_id",
    "/orders/": "order_id",
    "/orders/create/": "order_id",
    "/orders/my/": "order_id",
    "/partners/admin/applications/": "partner_application_id",
    "/partners/applications/": "partner_application_id",
}

PATH_PARAMETER_VARIABLES = {
    ("/catalog/addition-classifications/{classification_id}/", "classification_id"): (
        "addition_classification_id"
    ),
    ("/catalog/category-classifications/{classification_id}/", "classification_id"): (
        "category_classification_id"
    ),
    ("/catalog/product-categories/{category_id}/", "category_id"): (
        "product_category_id"
    ),
    ("/catalog/store-subcategories/{subcategory_id}/", "subcategory_id"): (
        "store_subcategory_id"
    ),
    ("/home/classifications/{classification_id}/markets/", "classification_id"): (
        "market_classification_id"
    ),
    ("/home/market-classifications/{classification_id}/", "classification_id"): (
        "market_classification_id"
    ),
    ("/locations/delivery-areas/{area_id}/", "area_id"): "delivery_area_id",
    ("/locations/service-cities/{city_id}/", "city_id"): "service_city_id",
    ("/locations/shipping-companies/{company_id}/", "company_id"): (
        "shipping_company_id"
    ),
    ("/partners/admin/applications/{application_id}/", "application_id"): (
        "partner_application_id"
    ),
}


COLLECTION_PREREQUEST_SCRIPT = [
    "const vars = pm.collectionVariables;",
    "if (!vars.get('run_suffix')) {",
    "  const suffix = String(Date.now()).slice(-8);",
    "  vars.set('run_suffix', suffix);",
    "  vars.set('signup_email', `postman.client+${suffix}@example.com`);",
    "  vars.set('signup_username', `postman_client_${suffix}`);",
    "  vars.set('signup_phone', `+2010${suffix}`);",
    "  vars.set('new_user_email', `postman.rep+${suffix}@example.com`);",
    "  vars.set('new_user_username', `postman_rep_${suffix}`);",
    "  vars.set('new_user_phone', `+2011${suffix}`);",
    "}",
    "const now = new Date();",
    "const offerStart = new Date(now.getTime() + 60 * 60 * 1000);",
    "const offerEnd = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);",
    "vars.set('offer_start_time', offerStart.toISOString());",
    "vars.set('offer_end_time', offerEnd.toISOString());",
    "vars.set('dashboard_from', `${now.getUTCFullYear()}-01-01`);",
    "vars.set('dashboard_to', now.toISOString().slice(0, 10));",
    "pm.request.headers.upsert({",
    "  key: 'X-Request-ID',",
    "  value: pm.variables.replaceIn('{{$guid}}'),",
    "});",
]

COLLECTION_TEST_SCRIPT = [
    "pm.test('No unhandled server error', function () {",
    "  pm.expect(pm.response.code).to.be.below(500);",
    "});",
    "const contentType = pm.response.headers.get('Content-Type') || '';",
    "if (contentType.includes('application/json') && pm.response.text()) {",
    "  pm.test('Response contains valid JSON', function () {",
    "    pm.expect(function () { pm.response.json(); }).not.to.throw();",
    "  });",
    "}",
]

SUCCESS_TEST_SCRIPT = [
    "pm.test('Successful HTTP status', function () {",
    "  pm.expect(pm.response.code).to.be.oneOf([200, 201, 202, 204]);",
    "});",
]

DESTRUCTIVE_GUARD_SCRIPT = [
    "if (pm.collectionVariables.get('allow_destructive_requests') !== 'true') {",
    "  console.warn('Skipped: set allow_destructive_requests=true to enable DELETE requests.');",
    "  if (pm.execution && pm.execution.skipRequest) {",
    "    pm.execution.skipRequest();",
    "  } else {",
    "    throw new Error('Destructive requests are disabled by collection variables.');",
    "  }",
    "}",
]

ACCOUNT_DELETE_GUARD_SCRIPT = [
    *DESTRUCTIVE_GUARD_SCRIPT,
    "if (pm.collectionVariables.get('allow_account_deletion') !== 'true') {",
    "  console.warn('Skipped: set allow_account_deletion=true to delete the client account.');",
    "  if (pm.execution && pm.execution.skipRequest) {",
    "    pm.execution.skipRequest();",
    "  } else {",
    "    throw new Error('Account deletion is disabled by collection variables.');",
    "  }",
    "}",
]


def event(listen: str, lines: list[str]) -> dict[str, Any]:
    return {
        "listen": listen,
        "script": {
            "type": "text/javascript",
            "exec": lines,
        },
    }


def bearer(variable: str) -> dict[str, Any]:
    return {
        "type": "bearer",
        "bearer": [{"key": "token", "value": f"{{{{{variable}}}}}", "type": "string"}],
    }


def role_for(method: str, path: str) -> str:
    if path in PUBLIC_API_PATHS:
        return "Public"
    if path.startswith("/admin/") or path.startswith("/dashboard/"):
        return "Admin"
    if path.startswith("/courier/"):
        return "Representative"
    if path.startswith("/auth/users/") or path == "/auth/representatives/":
        return "Admin"
    if path.startswith("/catalog/"):
        if path == "/catalog/products/likes/" or path.endswith(("/like/", "/unlike/")):
            return "Client"
        return "Admin"
    if path.startswith("/home/"):
        client_market_action = path.endswith(("/like/", "/unlike/", "/storefront/"))
        if client_market_action or path == "/home/markets/likes/":
            return "Client"
        if path.startswith(
            ("/home/market-classifications/", "/home/market-types/", "/home/markets/")
        ):
            return "Admin"
        return "Client"
    if path.startswith("/locations/service-cities/"):
        return "Admin"
    if path.startswith("/locations/delivery-areas/"):
        return "Client" if method == "GET" else "Admin"
    if path.startswith("/locations/shipping-companies/"):
        return "Client" if method == "GET" else "Admin"
    if path.startswith("/offers/"):
        return "Client" if method == "GET" else "Admin"
    if path.startswith("/orders/"):
        client_paths = {
            "/orders/my/",
            "/orders/preview/",
            "/orders/create/",
        }
        if path in client_paths or path.endswith("/delivery-price/accept/"):
            return "Client"
        return "Admin"
    if path.startswith("/partners/admin/"):
        return "Admin"
    return "Client"


def request_auth(method: str, path: str) -> dict[str, Any]:
    role = role_for(method, path)
    if role == "Public":
        return {"type": "noauth"}
    variable = {
        "Admin": "admin_access_token",
        "Client": "client_access_token",
        "Representative": "representative_access_token",
    }[role]
    return bearer(variable)


def folder_for(method: str, path: str) -> tuple[str, str]:
    if path.startswith("/auth/users/") or path == "/auth/representatives/":
        return "02 Admin Users", "Users & Representatives"
    if path.startswith("/auth/"):
        if path.startswith(("/auth/signup/", "/auth/verify-email/", "/auth/resend-verification/")):
            return "01 Authentication", "Registration"
        if path.startswith(("/auth/forgot-password/", "/auth/reset-password/")):
            return "01 Authentication", "Password Recovery"
        if path.startswith("/auth/check-"):
            return "01 Authentication", "Availability Checks"
        if path.startswith(("/auth/login", "/auth/refresh/", "/auth/logout/")):
            return "01 Authentication", "Login & Tokens"
        return "01 Authentication", "Profile"
    if path.startswith("/admin/"):
        return "09 Orders - Admin", "Review & Approval"
    if path.startswith("/addresses/"):
        return "03 Region & Locations", "Address Alias"
    if path.startswith("/market-region/"):
        return "03 Region & Locations", "Market Region"
    if path.startswith("/locations/"):
        segment = path.strip("/").split("/")[1]
        return "03 Region & Locations", segment.replace("-", " ").title()
    if path.startswith("/catalog/"):
        segment = path.strip("/").split("/")[1]
        if segment == "products" and path.endswith(("/like/", "/unlike/")):
            return "04 Storefront", "Product Likes"
        if path == "/catalog/products/likes/":
            return "04 Storefront", "Product Likes"
        return "06 Catalog Admin", segment.replace("-", " ").title()
    if path.startswith("/courier/"):
        return "10 Courier", "Orders"
    if path.startswith("/dashboard/"):
        return "13 Dashboard", "Dashboard"
    if path.startswith("/home/"):
        is_client_market = path.endswith(("/like/", "/unlike/", "/storefront/"))
        if is_client_market or path == "/home/markets/likes/":
            return "04 Storefront", "Markets"
        if path.startswith(
            ("/home/market-classifications/", "/home/market-types/", "/home/markets/")
        ):
            segment = path.strip("/").split("/")[1]
            return "05 Markets Admin", segment.replace("-", " ").title()
        return "04 Storefront", "Home & Discovery"
    if path.startswith("/notifications/"):
        return "11 Notifications", "Notifications"
    if path.startswith("/offers/"):
        return "07 Offers", "Offers"
    if path.startswith("/orders/"):
        if role_for(method, path) == "Client":
            return "08 Orders - Client", "Client Orders"
        return "09 Orders - Admin", "Order Management"
    if path.startswith("/partners/admin/"):
        return "12 Partners", "Admin Review"
    if path.startswith("/partners/"):
        return "12 Partners", "Applications"
    raise ValueError(f"No folder mapping for {method} {path}")


def human_request_name(method: str, path: str) -> str:
    override = NAME_OVERRIDES.get((method, path))
    if override:
        return override
    segments = []
    for segment in path.strip("/").split("/"):
        if segment in {
            "auth",
            "catalog",
            "home",
            "locations",
            "orders",
            "offers",
            "notifications",
            "partners",
            "courier",
            "dashboard",
            "addresses",
            "admin",
            "market-region",
        } and not segments:
            continue
        match = re.fullmatch(r"\{(.+)}", segment)
        if match:
            segments.append(f"by {match.group(1).replace('_', ' ')}")
        else:
            segments.append(segment.replace("-", " "))
    label = " / ".join(segments).title() or "Root"
    return f"{method} · {label}"


def query_for(method: str, path: str) -> list[dict[str, Any]]:
    query = [dict(item) for item in QUERY_EXAMPLES.get((method, path), [])]
    if method == "GET" and path in PAGINATED_PATHS:
        query.extend(
            [
                {
                    "key": "page",
                    "value": "1",
                    "description": "Used by v2 pagination; ignored by v1.",
                },
                {
                    "key": "page_size",
                    "value": "50",
                    "description": "v2 maximum is 100.",
                },
            ]
        )
    return query


def postman_url(base: str, path: str, query: list[dict[str, Any]]) -> dict[str, Any]:
    def replace_parameter(match: re.Match[str]) -> str:
        parameter = match.group(1)
        variable = PATH_PARAMETER_VARIABLES.get((path, parameter), parameter)
        return f"{{{{{variable}}}}}"

    variable_path = re.sub(r"\{([^}]+)}", replace_parameter, path)
    enabled = [item for item in query if not item.get("disabled")]
    query_string = "&".join(
        f"{item['key']}={item.get('value', '')}" for item in enabled
    )
    raw_url = f"{base}{variable_path}"
    if query_string:
        raw_url = f"{raw_url}?{query_string}"
    host = [base]
    return {
        "raw": raw_url,
        "host": host,
        "path": [part for part in variable_path.strip("/").split("/") if part],
        "query": query,
    }


def capture_script(method: str, path: str) -> list[str]:
    lines: list[str] = []
    if path in {
        "/auth/login/",
        "/auth/login/admin/",
        "/auth/login/client/",
        "/auth/login/representative/",
        "/auth/verify-email/",
    }:
        lines.extend(
            [
                "if (pm.response.code === 200) {",
                "  const data = pm.response.json();",
                "  const role = data.user && data.user.role ? data.user.role : 'client';",
                "  pm.collectionVariables.set('access_token', data.accessToken);",
                "  pm.collectionVariables.set('refresh_token', data.refreshToken);",
                "  if (role === 'admin') {",
                "    pm.collectionVariables.set('admin_access_token', data.accessToken);",
                "    pm.collectionVariables.set('admin_refresh_token', data.refreshToken);",
                "  } else if (role === 'representative') {",
                "    pm.collectionVariables.set('representative_access_token', data.accessToken);",
                "    pm.collectionVariables.set('representative_refresh_token', data.refreshToken);",
                "    if (data.user.id) pm.collectionVariables.set('representative_id', data.user.id);",
                "  } else {",
                "    pm.collectionVariables.set('client_access_token', data.accessToken);",
                "    pm.collectionVariables.set('client_refresh_token', data.refreshToken);",
                "    if (data.user.id) pm.collectionVariables.set('client_user_id', data.user.id);",
                "  }",
                "}",
            ]
        )
    if path == "/auth/signup/":
        lines.extend(
            [
                "if (pm.response.code === 201) {",
                "  const data = pm.response.json();",
                "  if (data.otp) pm.collectionVariables.set('registration_otp', String(data.otp));",
                "}",
            ]
        )
    if path == "/auth/forgot-password/":
        lines.extend(
            [
                "if (pm.response.code === 200) {",
                "  const data = pm.response.json();",
                "  if (data.otp) pm.collectionVariables.set('reset_otp', String(data.otp));",
                "}",
            ]
        )
    if path == "/auth/refresh/":
        lines.extend(
            [
                "if (pm.response.code === 200) {",
                "  const data = pm.response.json();",
                "  pm.collectionVariables.set('access_token', data.accessToken);",
                "  pm.collectionVariables.set('refresh_token', data.refreshToken);",
                "}",
            ]
        )
    variable = CAPTURE_IDS.get(path)
    if variable:
        overwrite = "true" if method == "POST" else "false"
        lines.extend(
            [
                "if (pm.response.code >= 200 && pm.response.code < 300 && pm.response.text()) {",
                "  const payload = pm.response.json();",
                "  const list = Array.isArray(payload) ? payload : (payload.results || null);",
                "  const entity = list ? list[0] : payload;",
                f"  const shouldOverwrite = {overwrite};",
                f"  if (entity && entity.id && (shouldOverwrite || !pm.collectionVariables.get('{variable}'))) {{",
                f"    pm.collectionVariables.set('{variable}', entity.id);",
                "  }",
                "  if (entity && Array.isArray(entity.variants) && entity.variants[0]) {",
                "    pm.collectionVariables.set('variant_id', entity.variants[0].id);",
                "  }",
                "  if (entity && Array.isArray(entity.images) && entity.images[0]) {",
                "    pm.collectionVariables.set('image_id', entity.images[0].id);",
                "  }",
                "  if (entity && Array.isArray(entity.subcategories) && entity.subcategories[0]) {",
                "    pm.collectionVariables.set('store_subcategory_id', entity.subcategories[0].id);",
                "  }",
                "}",
            ]
        )
    if path == "/catalog/products/{product_id}/images/" and method == "POST":
        lines.extend(
            [
                "if (pm.response.code >= 200 && pm.response.code < 300) {",
                "  const data = pm.response.json();",
                "  const image = Array.isArray(data) ? data[0] : data;",
                "  if (image && image.id) pm.collectionVariables.set('image_id', image.id);",
                "}",
            ]
        )
    return lines


def operation_description(method: str, path: str, operation: dict[str, Any]) -> str:
    role = role_for(method, path)
    response_codes = ", ".join(operation.get("responses", {}).keys()) or "runtime-defined"
    parts = [
        f"Access: {role}.",
        f"Documented response codes: {response_codes}.",
        "Change api_version to v1 or v2 without editing the request URL.",
    ]
    if method == "DELETE":
        parts.append(
            "Safety: skipped unless allow_destructive_requests=true. "
            "Client account deletion also requires allow_account_deletion=true."
        )
    if path.endswith(("/{market_id}/", "/{product_id}/", "/{offer_id}/")):
        parts.append('Archived resources can be restored with PATCH body {"restore": true}.')
    body = BODY_EXAMPLES.get((method, path))
    if body and body.get("mode") == "formdata":
        parts.append(
            "Multipart request: set sample_image_path and enable optional file rows when needed."
        )
    if operation.get("description"):
        parts.append(operation["description"].strip())
    return "\n\n".join(parts)


def request_item(
    method: str,
    path: str,
    operation: dict[str, Any],
) -> dict[str, Any]:
    query = query_for(method, path)
    request: dict[str, Any] = {
        "auth": request_auth(method, path),
        "method": method,
        "header": [{"key": "Accept", "value": "application/json", "type": "text"}],
        "url": postman_url("{{api_base}}", path, query),
        "description": operation_description(method, path, operation),
    }
    body = BODY_EXAMPLES.get((method, path))
    if body:
        request["body"] = body
        if body["mode"] == "raw":
            request["header"].append(
                {"key": "Content-Type", "value": "application/json", "type": "text"}
            )
    events = [event("test", [*SUCCESS_TEST_SCRIPT, *capture_script(method, path)])]
    if method == "DELETE":
        guard = (
            ACCOUNT_DELETE_GUARD_SCRIPT
            if path == "/auth/client/profile/"
            else DESTRUCTIVE_GUARD_SCRIPT
        )
        events.insert(0, event("prerequest", guard))
    return {
        "name": human_request_name(method, path),
        "event": events,
        "request": request,
        "response": [],
    }


def operation_sort_key(method: str, path: str) -> tuple[Any, ...]:
    auth_sequence = {
        ("POST", "/auth/login/"): 0,
        ("POST", "/auth/login/client/"): 1,
        ("POST", "/auth/login/admin/"): 2,
        ("POST", "/auth/login/representative/"): 3,
        ("POST", "/auth/refresh/"): 4,
        ("POST", "/auth/logout/"): 5,
    }
    if (method, path) in auth_sequence:
        return (False, False, 0, auth_sequence[(method, path)], 0)
    has_parameter = "{" in path
    is_delete = method == "DELETE"
    method_rank = {"GET": 0, "POST": 1, "PUT": 2, "PATCH": 3, "DELETE": 9}[method]
    depth = -path.count("/") if is_delete else path.count("/")
    return (is_delete, has_parameter, depth, path, method_rank)


def api_groups(schema: dict[str, Any]) -> tuple[dict[str, Any], set[tuple[str, str]]]:
    groups: dict[str, dict[str, list[tuple[str, str, dict[str, Any]]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    discovered: set[tuple[str, str]] = set()
    for full_path, path_item in schema["paths"].items():
        if not full_path.startswith(f"{API_SCHEMA_PREFIX}/"):
            continue
        path = full_path.removeprefix(API_SCHEMA_PREFIX)
        for raw_method, operation in path_item.items():
            if raw_method not in HTTP_METHODS:
                continue
            method = raw_method.upper()
            discovered.add((method, path))
            folder, subgroup = folder_for(method, path)
            groups[folder][subgroup].append((method, path, operation))
    return groups, discovered


def system_request(
    name: str,
    path: str,
    *,
    auth_variable: str | None = None,
    accept: str = "application/json",
    expected_codes: tuple[int, ...] = (200,),
) -> dict[str, Any]:
    request = {
        "auth": bearer(auth_variable) if auth_variable else {"type": "noauth"},
        "method": "GET",
        "header": [{"key": "Accept", "value": accept, "type": "text"}],
        "url": postman_url("{{base_url}}", path, []),
    }
    return {
        "name": name,
        "event": [
            event(
                "test",
                [
                    "pm.test('Expected system-route status', function () {",
                    f"  pm.expect(pm.response.code).to.be.oneOf({json.dumps(expected_codes)});",
                    "});",
                ],
            )
        ],
        "request": request,
        "response": [],
    }


def system_items() -> list[dict[str, Any]]:
    return [
        system_request("GET · Liveness", "/health/"),
        system_request("GET · Liveness alias", "/healthz/"),
        system_request("GET · Readiness", "/readyz/", expected_codes=(200, 503)),
        system_request("GET · Privacy policy", "/privacy/", accept="text/html"),
        system_request("GET · Terms of use", "/terms/", accept="text/html"),
        system_request(
            "GET · Account deletion instructions", "/account-deletion/", accept="text/html"
        ),
        system_request(
            "GET · Product share page",
            "/share/products/{{product_id}}/",
            accept="text/html",
            expected_codes=(200, 404),
        ),
        system_request(
            "GET · Offer share page",
            "/share/offers/{{offer_id}}/",
            accept="text/html",
            expected_codes=(200, 404),
        ),
        system_request(
            "GET · Market share page",
            "/share/markets/{{market_id}}/",
            accept="text/html",
            expected_codes=(200, 404),
        ),
        system_request(
            "GET · OpenAPI schema",
            "/api/schema/",
            auth_variable="admin_access_token",
            expected_codes=(200, 401, 403),
        ),
        system_request(
            "GET · Swagger UI",
            "/api/docs/",
            auth_variable="admin_access_token",
            accept="text/html",
            expected_codes=(200, 401, 403),
        ),
    ]


def scenario_item(
    name: str,
    method: str,
    path: str,
    expected_codes: list[int],
    *,
    payload: dict[str, Any] | None = None,
    auth: dict[str, Any] | None = None,
    description: str,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "auth": auth or {"type": "noauth"},
        "method": method,
        "header": [{"key": "Accept", "value": "application/json", "type": "text"}],
        "url": postman_url("{{api_base}}", path, []),
        "description": description,
    }
    if payload is not None:
        request["body"] = raw(payload)
        request["header"].append(
            {"key": "Content-Type", "value": "application/json", "type": "text"}
        )
    codes = json.dumps(expected_codes)
    tests = [
        "pm.test('Expected negative-scenario status', function () {",
        f"  pm.expect(pm.response.code).to.be.oneOf({codes});",
        "});",
    ]
    return {
        "name": name,
        "event": [event("test", tests)],
        "request": request,
        "response": [],
    }


def negative_scenarios() -> list[dict[str, Any]]:
    return [
        scenario_item(
            "401 · Client login with invalid password",
            "POST",
            "/auth/login/client/",
            [401],
            payload={
                "identifier": "{{client_email}}",
                "password": "DefinitelyWrong1!",
                "remember": False,
            },
            description="Valid identifier with an invalid password must not issue tokens.",
        ),
        scenario_item(
            "400 · Sign up without accepting terms",
            "POST",
            "/auth/signup/",
            [400],
            payload={
                "first_name": "Postman",
                "last_name": "Rejected",
                "username": "invalid_{{run_suffix}}",
                "email": "invalid+{{run_suffix}}@example.com",
                "phone": "+2012{{run_suffix}}",
                "password": "PostmanPass1!",
                "password_confirm": "PostmanPass1!",
                "terms_accepted": False,
            },
            description="Backend validation must reject terms_accepted=false.",
        ),
        scenario_item(
            "400 · Verify an invalid OTP",
            "POST",
            "/auth/verify-email/",
            [400],
            payload={"email": "{{signup_email}}", "otp": "000000"},
            description="A missing, expired, used, or incorrect OTP must be rejected.",
        ),
        scenario_item(
            "401 · Refresh with an invalid token",
            "POST",
            "/auth/refresh/",
            [401],
            payload={"refreshToken": "not-a-jwt"},
            description="Invalid refresh tokens must not rotate into valid credentials.",
        ),
        scenario_item(
            "401 · Protected endpoint without JWT",
            "GET",
            "/auth/me/",
            [401],
            description="Default DRF authentication must protect authenticated endpoints.",
        ),
        scenario_item(
            "403 · Client JWT on admin endpoint",
            "GET",
            "/dashboard/settings/",
            [401, 403],
            auth=bearer("client_access_token"),
            description=(
                "After Client Login this must return 403. It may return 401 when the "
                "client token variable has not been populated yet."
            ),
        ),
    ]


SUBGROUP_ORDER = {
    "01 Authentication": [
        "Registration",
        "Login & Tokens",
        "Password Recovery",
        "Availability Checks",
        "Profile",
        "Negative Security Scenarios",
    ],
    "03 Region & Locations": [
        "Market Region",
        "Service Cities",
        "Delivery Areas",
        "Geocoding",
        "Addresses",
        "Address Alias",
    ],
    "05 Markets Admin": ["Market Classifications", "Market Types", "Markets"],
    "06 Catalog Admin": [
        "Store Subcategories",
        "Category Classifications",
        "Product Categories",
        "Category Attributes",
        "Category Options",
        "Addition Classifications",
        "Product Additions",
        "Products",
    ],
}


def subgroup_sort_key(folder: str, subgroup: str) -> tuple[int, str]:
    configured = SUBGROUP_ORDER.get(folder, [])
    try:
        return configured.index(subgroup), subgroup
    except ValueError:
        return len(configured), subgroup


def build_collection(schema: dict[str, Any]) -> tuple[dict[str, Any], set[tuple[str, str]]]:
    groups, discovered = api_groups(schema)
    groups["01 Authentication"]["Negative Security Scenarios"] = []

    top_level: list[dict[str, Any]] = [
        {
            "name": "00 System & Public",
            "description": FOLDER_DESCRIPTIONS["00 System & Public"],
            "item": system_items(),
        }
    ]
    for folder in sorted(groups, key=lambda value: FOLDER_ORDER[value]):
        subfolders = []
        for subgroup in sorted(
            groups[folder], key=lambda value: subgroup_sort_key(folder, value)
        ):
            if subgroup == "Negative Security Scenarios":
                items = negative_scenarios()
            else:
                operations = sorted(
                    groups[folder][subgroup],
                    key=lambda value: operation_sort_key(value[0], value[1]),
                )
                items = [request_item(*operation) for operation in operations]
            subfolders.append({"name": subgroup, "item": items})
        top_level.append(
            {
                "name": folder,
                "description": FOLDER_DESCRIPTIONS[folder],
                "item": subfolders,
            }
        )

    description = """# Yalla Backend Postman Collection

Generated from `openapi.yml` plus request contracts extracted from serializers,
views, permissions, and tests.

## Quick start

1. Run `python manage.py seed_demo_data --reset --yes-delete-all` only against a
   disposable local database when you need the documented demo credentials.
2. Run Client Login, Admin Login, and Representative Login. Their scripts save
   role-specific access and refresh tokens automatically.
3. Keep `api_version=v2` for paginated lists, or switch it to `v1` for the
   compatibility API.
4. Set `sample_image_path` before running multipart upload requests.
5. DELETE requests are skipped by default. Explicitly set
   `allow_destructive_requests=true` to enable them. Account deletion has a
   second independent guard: `allow_account_deletion=true`.

OTP values are captured automatically only when local development enables
`AUTH_OTP_INCLUDE_IN_RESPONSE`; otherwise copy the OTP from email into the
corresponding collection variable.
"""
    collection = {
        "info": {
            "_postman_id": "858714c2-a7d7-4fc9-9977-b25ccb8dbec5",
            "name": "Yalla Backend APIs - Complete",
            "description": description,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "auth": {"type": "noauth"},
        "event": [
            event("prerequest", COLLECTION_PREREQUEST_SCRIPT),
            event("test", COLLECTION_TEST_SCRIPT),
        ],
        "variable": [
            {"key": key, "value": value, "type": variable_type}
            for key, value, variable_type in COLLECTION_VARIABLES
        ],
        "item": top_level,
    }
    return collection, discovered


def validate_contract(discovered: set[tuple[str, str]]) -> None:
    mutations = {
        operation
        for operation in discovered
        if operation[0] in {"POST", "PUT", "PATCH"}
    }
    missing_bodies = sorted(
        mutations - set(BODY_EXAMPLES) - EMPTY_BODY_OPERATIONS
    )
    if missing_bodies:
        formatted = "\n".join(f"{method} {path}" for method, path in missing_bodies)
        raise RuntimeError(f"Mutation examples are missing:\n{formatted}")

    unknown_bodies = sorted(set(BODY_EXAMPLES) - discovered)
    if unknown_bodies:
        formatted = "\n".join(f"{method} {path}" for method, path in unknown_bodies)
        raise RuntimeError(f"Body examples reference unknown operations:\n{formatted}")

    v1_operations = set()
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    for full_path, path_item in schema["paths"].items():
        if not full_path.startswith("/api/v1/"):
            continue
        path = full_path.removeprefix("/api/v1")
        for method in path_item:
            if method in HTTP_METHODS:
                v1_operations.add((method.upper(), path))
    if discovered != v1_operations:
        only_v2 = sorted(discovered - v1_operations)
        only_v1 = sorted(v1_operations - discovered)
        raise RuntimeError(
            "v1/v2 operation mismatch. "
            f"Only v2: {only_v2}; only v1: {only_v1}"
        )


def validate_collection(collection: dict[str, Any]) -> None:
    requests: list[dict[str, Any]] = []

    def visit(items: list[dict[str, Any]]) -> None:
        for item in items:
            if "request" in item:
                requests.append(item)
            else:
                visit(item.get("item", []))

    visit(collection["item"])
    for item in requests:
        body = item["request"].get("body", {})
        if body.get("mode") == "raw":
            json.loads(body["raw"])

    variables = {item["key"] for item in collection["variable"]}
    serialized = json.dumps(collection, ensure_ascii=False)
    references = {
        value
        for value in re.findall(r"(?<!\{)\{\{([^{}]+)\}\}", serialized)
        if not value.startswith("$")
    }
    if unknown := sorted(references - variables):
        raise RuntimeError(f"Unknown Postman variables: {unknown}")

    unguarded_deletes = [
        item["name"]
        for item in requests
        if item["request"]["method"] == "DELETE"
        and not any(entry.get("listen") == "prerequest" for entry in item.get("event", []))
    ]
    if unguarded_deletes:
        raise RuntimeError(f"DELETE requests are missing safety guards: {unguarded_deletes}")


def main() -> None:
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    collection, discovered = build_collection(schema)
    validate_contract(discovered)
    validate_collection(collection)
    OUTPUT_PATH.write_text(
        json.dumps(collection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Generated {OUTPUT_PATH.relative_to(ROOT)} with "
        f"{len(discovered)} versioned API operations."
    )


if __name__ == "__main__":
    main()
