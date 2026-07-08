# API Report

## 1. Metadata

- generated_at: 2026-07-08T12:39:14+02:00
- git branch: main
- git commit: 0f9559f0c1560dbff909d6ad4b874f3d99db2fee
- Python version: 3.12.3 from `.venv/bin/python`
- Django version: 6.0.6
- DRF version: 3.17.1
- database used for verification: `config.test_settings`, SQLite `:memory:`
- media storage used for captured examples: temporary local `FileSystemStorage` override, because default/test settings use Cloudinary storage when `DEBUG=False`
- primary discovery sources: `config/urls.py`, app URL modules, views, serializers, models, services, tests, Django URL resolver, and live DRF `APIClient` calls against an in-memory migrated database
- existing `API_REPORT.md`: not used as source of truth; replaced

Commands run:

```bash
rtk git status --short --branch
rtk git rev-parse --abbrev-ref HEAD
rtk git rev-parse HEAD
rtk .venv/bin/python --version
rtk .venv/bin/python -c "import django, rest_framework; print(django.get_version()); print(rest_framework.VERSION)"
rtk .venv/bin/python manage.py makemigrations --check --dry-run
rtk .venv/bin/python manage.py test --settings=config.test_settings
rtk proxy .venv/bin/python - <<'PY'  # URL resolver endpoint inventory
rtk .venv/bin/python api_report_capture_tmp.py  # temporary APIClient capture script; removed after use
```

Test result summary:

- `makemigrations --check --dry-run`: passed, `No changes detected`; emitted warning that `DATABASE_URL` is not set.
- `manage.py test --settings=config.test_settings`: failed after running 306 tests in 485.897s: 1 failure, 7 errors.
- The 7 errors are upload tests that attempted Cloudinary writes without Cloudinary API credentials under `config.test_settings`.
- The 1 failure is `accounts.tests_seed.SeedDataCommandTests.test_seed_data_populates_every_project_model`: `orders.OrderEvent` was empty after `seed_data`.
- Live API examples below were captured successfully with a temporary storage override; backend behavior was not changed.

Example provenance:

- Code blocks labelled "Captured" came from real DRF `APIClient` requests in the temporary verification DB.
- Field lists, writable/read-only rules, and choices are from serializers/models/views.
- Anything not proven by code or captured response is marked `Unconfirmed`.

## 2. Global API Rules

Base URL:

- All application endpoints are under `/api/v1/`.
- Auth endpoints often have both slash and no-slash aliases, for example `/api/v1/auth/login` and `/api/v1/auth/login/`.
- Non-auth app endpoints are slash-terminated.

Authentication:

- JWT via `rest_framework_simplejwt.authentication.JWTAuthentication`.
- Header format: `Authorization: Bearer <accessToken>`.
- Login response keys: `accessToken`, `refreshToken`, `expiresIn`, `user`.
- Access token lifetime: 900 seconds.
- Refresh token lifetime: 30 days, with refresh rotation and blacklist enabled.

Common response/data formats:

- IDs are integer values for domain models except auth `UserSerializer.id`, which serializes as a string.
- Datetimes serialize as ISO 8601 UTC strings, for example `2026-07-08T10:37:43.096314Z`.
- Dates use `YYYY-MM-DD`.
- Decimal/money fields serialize as strings with fixed decimal places, for example `"120.00"`.
- Booleans in JSON are real booleans. Multipart booleans accept strings such as `"true"` / `"false"` where DRF BooleanField is used.
- File/image fields may be `null`, a `/media/...` path, or a fully qualified URL depending on storage/request context.
- Do not manually set multipart `Content-Type` from the frontend; let the browser set the boundary.

Pagination:

- Only the home product list/search endpoints use DRF page-number pagination in the inspected code.
- Shape:

```json
{
  "count": 21,
  "next": "http://testserver/api/v1/home/search/?page=2&q=Product",
  "previous": null,
  "results": []
}
```

- Page size is 4 for `/api/v1/home/search/` and `/api/v1/home/products/`.

Common error shape:

- DRF validation errors are field-keyed arrays:

```json
{
  "payment_method": ["This field is required."]
}
```

- Permission/auth errors use `detail`:

```json
{"detail": "Authentication credentials were not provided."}
```

- Some order region errors are returned through `serializers.ValidationError` with scalar values converted to string arrays:

```json
{
  "requires_region_selection": ["True"],
  "message": ["Select a market browsing region before checkout."],
  "current_selection": ["None"]
}
```

Localized/Arabic errors:

- Arabic validation messages are present in order, location, and courier assignment flows. They are API contract values, not frontend-only translations.
- Examples:
  - `لا يمكن دمج محلات عامة مع محلات مدينة في نفس الطلب`
  - `لا يمكن استخدام عرض مدينة داخل طلب عام`
  - `لا يمكن استخدام عرض عام داخل طلب مدينة`
  - `لا يمكن دمج منتجات من مدن مختلفة في نفس الطلب`
  - `هذا المندوب لا يعمل في نفس مدينة الطلب.`

Endpoint index:

| Endpoint | Methods | Permission |
|---|---:|---|
| `/api/v1/auth/signup`, `/signup/` | POST | public |
| `/api/v1/auth/verify-email`, `/verify-email/` | POST | public |
| `/api/v1/auth/resend-verification`, `/resend-verification/` | POST | public |
| `/api/v1/auth/login`, `/login/` | POST | public |
| `/api/v1/auth/login/client`, `/login/client/` | POST | public, client role required after credential validation |
| `/api/v1/auth/login/representative`, `/login/representative/` | POST | public, representative role required |
| `/api/v1/auth/login/admin`, `/login/admin/` | POST | public, admin role required |
| `/api/v1/auth/refresh`, `/refresh/` | POST | public |
| `/api/v1/auth/logout`, `/logout/` | POST | authenticated |
| `/api/v1/auth/me`, `/me/` | GET, PATCH, DELETE | authenticated |
| `/api/v1/auth/client/profile`, `/client/profile/` | PUT, PATCH | authenticated client |
| `/api/v1/auth/users`, `/users/` | GET, POST | authenticated admin |
| `/api/v1/auth/users/{user_id}`, `/users/{user_id}/` | GET, PATCH, DELETE | authenticated admin |
| `/api/v1/auth/representatives/` | GET | authenticated admin |
| `/api/v1/auth/check-username`, `/check-username/` | GET | public |
| `/api/v1/auth/check-email`, `/check-email/` | GET | public |
| `/api/v1/auth/check-phone`, `/check-phone/` | GET | public |
| `/api/v1/auth/forgot-password`, `/forgot-password/` | POST | public |
| `/api/v1/auth/reset-password`, `/reset-password/` | POST | public |
| `/api/v1/locations/service-cities/` | GET, POST | authenticated admin |
| `/api/v1/locations/service-cities/{city_id}/` | GET, PUT, PATCH, DELETE | authenticated admin |
| `/api/v1/locations/delivery-areas/` | GET, POST | GET authenticated; writes admin |
| `/api/v1/locations/delivery-areas/{area_id}/` | GET, PUT, PATCH, DELETE | GET authenticated; writes admin |
| `/api/v1/addresses/` | GET, POST | authenticated |
| `/api/v1/addresses/default/` | GET | authenticated |
| `/api/v1/addresses/{address_id}/` | PATCH, DELETE | authenticated owner or admin |
| `/api/v1/addresses/{address_id}/default/` | PATCH | authenticated owner or admin |
| `/api/v1/locations/addresses/...` | same as `/api/v1/addresses/...` | authenticated alias |
| `/api/v1/home/login-dashboard-snapshot/` | GET | public |
| `/api/v1/home/market-classifications/` | GET, POST | authenticated admin |
| `/api/v1/home/market-classifications/{classification_id}/` | GET, PATCH, DELETE | authenticated admin |
| `/api/v1/home/markets/` | GET, POST | authenticated admin |
| `/api/v1/home/markets/{market_id}/` | GET, PATCH, DELETE | authenticated admin |
| `/api/v1/home/` | GET | authenticated, selected market region required |
| `/api/v1/home/search/` | GET | authenticated, selected market region required |
| `/api/v1/home/products/` | GET | authenticated client, selected market region required |
| `/api/v1/home/products/{product_id}/` | GET | authenticated, selected market region required |
| `/api/v1/home/classifications/` | GET | authenticated, selected market region required |
| `/api/v1/home/classifications/featured/` | GET | authenticated, selected market region required |
| `/api/v1/home/classifications/popular/` | GET | authenticated, selected market region required |
| `/api/v1/home/classifications/normal/` | GET | authenticated, selected market region required |
| `/api/v1/home/classifications/{classification_id}/markets/` | GET | authenticated, selected market region required |
| `/api/v1/market-region/options/` | GET | authenticated |
| `/api/v1/market-region/me/` | GET, PATCH | authenticated |
| `/api/v1/market-region/detect/` | POST | authenticated |
| `/api/v1/catalog/addition-classifications/` | GET, POST | authenticated admin |
| `/api/v1/catalog/addition-classifications/{classification_id}/` | GET, PATCH, DELETE | authenticated admin |
| `/api/v1/catalog/category-classifications/` | GET, POST | authenticated admin |
| `/api/v1/catalog/category-classifications/{classification_id}/` | GET, PATCH, DELETE | authenticated admin |
| `/api/v1/catalog/product-categories/` | GET, POST | authenticated admin |
| `/api/v1/catalog/product-categories/{category_id}/` | GET, PATCH, DELETE | authenticated admin |
| `/api/v1/catalog/category-attributes/` | GET, POST | authenticated admin |
| `/api/v1/catalog/category-attributes/{attribute_id}/` | GET, PATCH, DELETE | authenticated admin |
| `/api/v1/catalog/category-options/` | GET, POST | authenticated admin |
| `/api/v1/catalog/category-options/{option_id}/` | GET, PATCH, DELETE | authenticated admin |
| `/api/v1/catalog/products/` | GET, POST | authenticated admin |
| `/api/v1/catalog/products/{product_id}/` | GET, PATCH, DELETE | authenticated admin |
| `/api/v1/catalog/products/likes/` | GET | authenticated client |
| `/api/v1/catalog/products/{product_id}/like/` | POST | authenticated client |
| `/api/v1/catalog/products/{product_id}/unlike/` | DELETE | authenticated client |
| `/api/v1/catalog/product-additions/` | GET, POST | authenticated admin |
| `/api/v1/catalog/product-additions/{addition_id}/` | GET, PATCH, DELETE | authenticated admin |
| `/api/v1/offers/` | GET, POST | GET admin/client; POST admin |
| `/api/v1/offers/{offer_id}/` | GET, PATCH, DELETE | GET admin/client; writes admin |
| `/api/v1/orders/` | GET, POST | authenticated admin |
| `/api/v1/orders/{order_id}/` | GET, PUT, PATCH, DELETE | authenticated admin |
| `/api/v1/orders/{order_id}/status/` | PATCH | authenticated admin |
| `/api/v1/orders/{order_id}/delivery-price/` | PATCH | authenticated admin |
| `/api/v1/orders/{order_id}/assignment/` | PATCH | authenticated admin |
| `/api/v1/orders/my/` | GET | authenticated client |
| `/api/v1/orders/preview/` | POST | authenticated client or admin-with-user_id by code |
| `/api/v1/orders/create/` | POST | authenticated client |
| `/api/v1/admin/order-review/blocker/` | GET | authenticated admin |
| `/api/v1/admin/orders/{order_id}/approve/` | POST | authenticated admin |
| `/api/v1/admin/orders/{order_id}/reject/` | POST | authenticated admin |
| `/api/v1/admin/orders/{order_id}/service-city-representatives/` | GET | authenticated admin |
| `/api/v1/courier/orders/` | GET | authenticated representative |
| `/api/v1/courier/orders/{order_id}/` | GET | authenticated assigned representative |
| `/api/v1/courier/orders/{order_id}/status/` | PATCH | authenticated assigned representative |
| `/api/v1/notifications/` | GET | authenticated |
| `/api/v1/notifications/unread-count/` | GET | authenticated |
| `/api/v1/notifications/{notification_id}/read/` | PATCH | authenticated visible notification |
| `/api/v1/notifications/mark-all-read/` | POST | authenticated |
| `/api/v1/notifications/clear-read/` | DELETE | authenticated |
| `/api/v1/notifications/{notification_id}/` | DELETE | authenticated visible notification |
| `/api/v1/dashboard/overview/` | GET | authenticated admin |
| `/api/v1/dashboard/settings/` | GET, PATCH | authenticated admin |

## 3. Auth / Accounts

Login request:

```json
{
  "email": "api-admin@example.com",
  "password": "Password1!"
}
```

Captured login response:

```json
{
  "accessToken": "<JWT redacted>",
  "refreshToken": "<JWT redacted>",
  "expiresIn": 900,
  "user": {
    "id": "1",
    "first_name": "",
    "last_name": "",
    "username": "api_admin",
    "email": "api-admin@example.com",
    "phone": "+213555100001",
    "gender": "",
    "birth_date": null,
    "avatar_url": null,
    "username_changed_at": null,
    "role": "admin",
    "has_password": true,
    "courier_profile": null
  }
}
```

Auth/account contracts:

| Endpoint | Request fields | Response |
|---|---|---|
| `POST /auth/signup` | `first_name`, `last_name`, `username`, `email`, `phone`, `password`, `password_confirm`, `terms_accepted` | `detail`, `email`, OTP cooldown fields, and `dev_otp` only when `AUTH_OTP_INCLUDE_IN_RESPONSE=True` |
| `POST /auth/verify-email` | `email`, `otp` | login token payload |
| `POST /auth/resend-verification` | `email` | `detail`, cooldown fields, optional `dev_otp` |
| `POST /auth/login*` | `email` or `identifier`, `password` | token payload |
| `POST /auth/refresh` | `refresh` or `refreshToken` | `accessToken`, `refreshToken` |
| `POST /auth/logout` | `refresh` or `refreshToken` | `{"detail": "Logout successful."}` |
| `GET /auth/me` | none | `UserSerializer` |
| `PATCH /auth/me` | profile fields below | `UserSerializer` |
| `DELETE /auth/me` | `password` | `{"detail": "Account deleted."}` |
| `PATCH/PUT /auth/client/profile` | same profile fields | `UserSerializer`; client role only |
| `GET /auth/users` | none | list of `AdminUserSerializer` |
| `POST /auth/users` | admin user write fields | `AdminUserSerializer` |
| `GET/PATCH/DELETE /auth/users/{id}` | admin user write fields for PATCH | detail/stats for GET/PATCH, 204 for DELETE |
| `GET /auth/representatives/` | none | admin user list filtered to representatives |
| `GET /auth/check-username` | query `username`, optional `exclude_user_id` for admin | `{available, registered}` |
| `GET /auth/check-email` | query `email`, optional `exclude_user_id` for admin | `{available, registered}` |
| `GET /auth/check-phone` | query `phone`, optional `exclude_user_id` for admin | `{available, registered}` |
| `POST /auth/forgot-password` | `email` | generic `detail`, cooldown fields if user exists |
| `POST /auth/reset-password` | `email`, `otp`, `password`, `password_confirm` | `{"detail": "Password reset successfully."}` |

User profile writable fields:

- `first_name`, `last_name`, `username`, `email`, `phone`, `gender`, `birth_date`, `avatar_url`
- multipart image field on user self/profile: `avatar`
- admin-only user write: `password`, `role`, `is_active`, `is_staff`, `is_superuser`, `avatar_image`, `courier_profile`

Courier profile writable fields inside admin user create/update:

```json
{
  "courier_profile": {
    "vehicle_type": "Motorcycle",
    "plate_number": "ABC123",
    "service_city": 1,
    "delivery_area": null,
    "max_active_orders": 3,
    "is_available": true
  }
}
```

Read-only/calculated auth fields:

- `id`, `avatar_url` when built from uploaded image, `has_password`, `username_changed_at`, nested `courier_profile.service_city_name`, admin `last_login`, `created_at`, `updated_at`, `customer_stats`, `recent_orders`.

Notable validation:

- Phone accepts Egypt and Algeria mobile formats and normalizes to `+20...` or `+213...`.
- Password must be at least 8 chars and include uppercase, number, and special char.
- Username can be changed only once every 7 days.
- Avatar/profile image extensions allowed by serializer: jpg, jpeg, png, webp; max 5 MB.

## 4. Locations

Endpoints:

| Endpoint | Methods | Permission | Query params |
|---|---:|---|---|
| `/api/v1/locations/service-cities/` | GET, POST | admin | none |
| `/api/v1/locations/service-cities/{city_id}/` | GET, PUT, PATCH, DELETE | admin | none |
| `/api/v1/locations/delivery-areas/` | GET, POST | GET authenticated, writes admin | `service_city_id` |
| `/api/v1/locations/delivery-areas/{area_id}/` | GET, PUT, PATCH, DELETE | GET authenticated, writes admin | none |
| `/api/v1/addresses/` | GET, POST | authenticated | admin can filter `user_id` |
| `/api/v1/addresses/default/` | GET | authenticated | none |
| `/api/v1/addresses/{address_id}/` | PATCH, DELETE | owner or admin | none |
| `/api/v1/addresses/{address_id}/default/` | PATCH | owner or admin | none |
| `/api/v1/locations/addresses/...` | same | authenticated alias | same |

Service city fields:

- Writable: `name`, `center_latitude`, `center_longitude`, `radius_km`, `delivery_price`, `is_active`
- Read-only/calculated: `id`, `delivery_area_count`, `market_count`, `offer_count`

Captured service-city list:

```json
[
  {
    "id": 1,
    "name": "API City",
    "center_latitude": "36.7525000",
    "center_longitude": "3.0420000",
    "radius_km": "20.00",
    "delivery_price": "120.00",
    "is_active": true,
    "delivery_area_count": 1,
    "market_count": 0,
    "offer_count": 0
  }
]
```

Delivery area fields:

- Writable: `service_city_id`, `name`, `center_latitude`, `center_longitude`, `radius_km`, `delivery_price`, `is_active`
- Read-only: `id`

Captured delivery areas by city:

```json
[
  {
    "id": 1,
    "service_city_id": 1,
    "name": "API Central",
    "center_latitude": "36.7525000",
    "center_longitude": "3.0420000",
    "radius_km": "5.00",
    "delivery_price": "120.00",
    "is_active": true
  }
]
```

Address writable fields:

- `user_id` only for admin create/update
- `service_city_id`, `delivery_area_id`, `delivery_type`
- `name`, `details`, `manual_city`, `manual_area`
- aliases accepted: `fullName`, `full_name`, `line1`, `street`, `address`, `city`, `state`, `country`, `postalCode`, `postal_code`, `isDefault`
- `latitude`, `longitude`, `is_default`

Address response shape:

- `id`, `name`, `fullName`, `phone`, `phoneNumber`, `line1`, `street`, `city`, `state`, `country`, `postalCode`
- `latitude`, `longitude`, `details`, `manual_city`, `manual_area`
- `service_city`, `service_city_id`, `service_city_name`
- `delivery_area`, `delivery_area_id`, `delivery_area_name`, `delivery_area_price`
- `delivery_type`, `delivery_price_preview`, `is_default`, `isDefault`, `created_at`

Delivery behavior rules:

- General/manual address:
  - `service_city = null`
  - `delivery_area = null`
  - `manual_city` and `manual_area` are plain text
  - `delivery_type = "delivery"`
  - `delivery_price_preview = null`
- Service-city fixed area:
  - `service_city` exists
  - `delivery_area` exists
  - `delivery_type = "fixed_area"`
  - `delivery_price_preview` comes from `delivery_area.delivery_price`
- Service-city manual unsupported area:
  - `service_city` exists
  - `delivery_area = null`
  - `manual_area` text
  - `delivery_type = "delivery"`
  - `delivery_price_preview = null`

Captured fixed-area address create:

```json
{
  "request": {
    "name": "Home",
    "line1": "1 API Street",
    "service_city_id": 1,
    "delivery_area_id": 1,
    "latitude": "36.7525000",
    "longitude": "3.0420000",
    "is_default": true
  },
  "response_item": {
    "id": 1,
    "name": "Home",
    "line1": "1 API Street",
    "manual_city": null,
    "manual_area": null,
    "service_city_id": 1,
    "delivery_area_id": 1,
    "delivery_type": "fixed_area",
    "delivery_price_preview": "120.00",
    "is_default": true
  }
}
```

Captured general/manual address item:

```json
{
  "id": 2,
  "name": "General Home",
  "line1": "Manual delivery street",
  "manual_city": "Mansoura",
  "manual_area": "University district",
  "service_city": null,
  "service_city_id": null,
  "delivery_area": null,
  "delivery_area_id": null,
  "delivery_type": "delivery",
  "delivery_price_preview": null
}
```

Delete behavior:

- Address delete is soft delete: `is_active=False`; response returns remaining active addresses.
- Service city delete is blocked when linked rows exist and returns:

```json
{
  "detail": "لا يمكن حذف المدينة لوجود بيانات مرتبطة بها.",
  "code": "service_city_in_use",
  "relations": {"delivery_areas": 1}
}
```

## 5. Markets / Shops

Endpoints:

| Endpoint | Methods | Permission |
|---|---:|---|
| `/api/v1/home/market-classifications/` | GET, POST | admin |
| `/api/v1/home/market-classifications/{classification_id}/` | GET, PATCH, DELETE | admin |
| `/api/v1/home/markets/` | GET, POST | admin |
| `/api/v1/home/markets/{market_id}/` | GET, PATCH, DELETE | admin |
| `/api/v1/home/` and classification/home product endpoints | GET | authenticated customer/admin with selected market region |

Market classification choices:

- `classification_type`: `popular`, `featured`, `normal`

Market choices:

- `scope`: `general`, `service_city`
- `status`: `active`, `inactive`

Admin market writable fields:

- `classification_id`, `name`, `branch`, `scope`, `status`
- `service_city_ids` or `service_cities`
- `delivery_area_ids` or `delivery_areas`

Read-only / response fields:

- `id`, nested `classification`, `service_cities`, `delivery_areas`, `created_at`, `updated_at`
- There is no market image field in the current model/serializer/API.

Captured general market create:

```json
{
  "request": {
    "classification_id": 1,
    "name": "API General Market",
    "branch": "Main",
    "scope": "general",
    "status": "active"
  },
  "response": {
    "id": 1,
    "classification": {"id": 1, "name": "API Markets", "classification_type": "featured"},
    "name": "API General Market",
    "branch": "Main",
    "scope": "general",
    "status": "active",
    "service_cities": [],
    "delivery_areas": []
  }
}
```

Captured service-city market create:

```json
{
  "request": {
    "classification_id": 1,
    "name": "API Service Market",
    "branch": "Central",
    "scope": "service_city",
    "status": "active",
    "service_city_ids": [1],
    "delivery_area_ids": [1]
  },
  "response": {
    "id": 2,
    "scope": "service_city",
    "service_cities": [{"id": 1, "name": "API City", "delivery_price": "120.00", "is_active": true}],
    "delivery_areas": [{"id": 1, "service_city_id": 1, "name": "API Central", "delivery_price": "120.00", "is_active": true}]
  }
}
```

Important current behavior:

- For `scope="service_city"`, at least one service city is required on create unless service cities are inferred from delivery areas.
- For `scope="general"`, the serializer does not require service cities or delivery areas.
- Current code does not forcibly clear `service_city_ids` / `delivery_area_ids` if sent for a general market. Dashboard should omit them for general markets to preserve the intended contract: general markets are not tied to fixed service-city delivery areas.

Home/market region endpoints:

- `/api/v1/market-region/options/`: returns general option plus active service-city options.
- `/api/v1/market-region/me/`: get or patch selected region.
- `/api/v1/market-region/detect/`: detects service city from coordinates and returns an action such as `same_region`, `select_detected_region`, `suggest_switch`, or `unsupported_location`.

## 6. Catalog / Products

Endpoints:

| Endpoint | Methods | Permission |
|---|---:|---|
| `/api/v1/catalog/category-classifications/` | GET, POST | admin |
| `/api/v1/catalog/category-classifications/{classification_id}/` | GET, PATCH, DELETE | admin |
| `/api/v1/catalog/product-categories/` | GET, POST | admin |
| `/api/v1/catalog/product-categories/{category_id}/` | GET, PATCH, DELETE | admin |
| `/api/v1/catalog/category-attributes/` | GET, POST | admin |
| `/api/v1/catalog/category-attributes/{attribute_id}/` | GET, PATCH, DELETE | admin |
| `/api/v1/catalog/category-options/` | GET, POST | admin |
| `/api/v1/catalog/category-options/{option_id}/` | GET, PATCH, DELETE | admin |
| `/api/v1/catalog/addition-classifications/` | GET, POST | admin |
| `/api/v1/catalog/addition-classifications/{classification_id}/` | GET, PATCH, DELETE | admin |
| `/api/v1/catalog/product-additions/` | GET, POST | admin |
| `/api/v1/catalog/product-additions/{addition_id}/` | GET, PATCH, DELETE | admin |
| `/api/v1/catalog/products/` | GET, POST | admin |
| `/api/v1/catalog/products/{product_id}/` | GET, PATCH, DELETE | admin |
| `/api/v1/catalog/products/likes/` | GET | client |
| `/api/v1/catalog/products/{product_id}/like/` | POST | client |
| `/api/v1/catalog/products/{product_id}/unlike/` | DELETE | client |
| `/api/v1/home/products/{product_id}/` | GET | authenticated visible product detail |

Product category fields:

- Writable: `classification_id`, `name`, `type`, `description`, `image`
- Response: `id`, nested `classification`, `name`, `type`, `description`, `image`
- Multipart image upload is supported and captured.

Captured category JSON create:

```json
{
  "classification_id": 1,
  "name": "API Meals",
  "type": "food",
  "description": "Meals category"
}
```

Captured category multipart create:

```json
{
  "classification_id": 1,
  "name": "API Drinks",
  "type": "drink",
  "description": "Drinks category",
  "image": "category.gif"
}
```

Response:

```json
{
  "id": 2,
  "classification": {"id": 1, "name": "API Categories"},
  "name": "API Drinks",
  "type": "drink",
  "description": "Drinks category",
  "image": "/media/categories/category.gif"
}
```

Product writable fields:

- `market_id`
- `category_id`
- `is_available`
- `name`
- `description`
- `image`
- `discount`
- `attribute_values`: array of `{attribute_id, option_id}`
- `variants`: array of `{price, sku, attribute_values: [{attribute_id, option_id}]}`
- `additions`: array of product addition IDs

Product response fields:

- Admin: `id`, nested `market`, nested `category`, `is_available`, `name`, `description`, `image`, `discount`, `attribute_values`, `variants`, `additions`, `created_at`, `updated_at`
- Home detail: `id`, `name`, `description`, `image`, `discount`, nested `category`, nested `market`, `variants`, `attribute_values`, nested `additions`, `created_at`, `updated_at`
- Product price is not a top-level API field. Current product price comes from `variants[].price`.

Backend-calculated/read-only:

- `id`, nested `market`, nested `category`, `created_at`, `updated_at`
- Variant `id` is read-only.
- Product/category nested representations are read-only.

Variant update rule:

- `PATCH /api/v1/catalog/products/{id}/` with a `variants` array deletes all existing variants and recreates them.
- Variant IDs cannot be preserved through the current serializer; `id` is read-only and not used for update matching.

Additions:

- JSON body: send `additions` as an array of IDs.
- Captured multipart body with image: `additions` as repeated/list form values works through DRF multipart parsing.
- Invalid type returns:

```json
{"additions": ["Expected a list of items but got type \"str\"."]}
```

Captured product JSON create without image:

```json
{
  "market_id": 2,
  "category_id": 1,
  "is_available": true,
  "name": "API Burger",
  "description": "Burger description",
  "discount": "5.00",
  "additions": [1],
  "attribute_values": [{"attribute_id": 1, "option_id": 1}],
  "variants": [
    {
      "price": "600.00",
      "sku": "BURGER-S",
      "attribute_values": [{"attribute_id": 1, "option_id": 1}]
    }
  ]
}
```

Captured product response excerpt:

```json
{
  "id": 1,
  "market": {"id": 2, "name": "API Service Market", "branch": "Central", "status": "active", "classification_id": 1},
  "category": {"id": 1, "name": "API Meals", "type": "food", "description": "Meals category", "image": null},
  "is_available": true,
  "name": "API Burger",
  "description": "Burger description",
  "image": null,
  "discount": "5.00",
  "attribute_values": [{"id": 1, "option": {"id": 1, "value": "Small"}}],
  "variants": [{"id": 1, "price": "600.00", "sku": "BURGER-S"}],
  "additions": [1],
  "created_at": "2026-07-08T10:37:43.096314Z",
  "updated_at": "2026-07-08T10:37:43.096344Z"
}
```

Captured product multipart with image:

```json
{
  "market_id": 2,
  "category_id": 1,
  "is_available": "true",
  "name": "API Product Image",
  "description": "Image product",
  "discount": "0.00",
  "additions": [1],
  "image": "product.gif"
}
```

Response excerpt:

```json
{
  "id": 2,
  "image": "/media/products/product.gif",
  "attribute_values": [],
  "variants": [],
  "additions": [1]
}
```

Home product detail with variants/additions:

```json
{
  "id": 1,
  "name": "API Burger",
  "discount": "5.00",
  "variants": [
    {
      "id": 1,
      "price": "600.00",
      "sku": "BURGER-S",
      "attribute_values": [
        {"id": 1, "attribute_id": 1, "attribute_name": "Size", "option_id": 1, "option_value": "Small"}
      ]
    }
  ],
  "additions": [
    {
      "id": 1,
      "classification_id": 1,
      "classification_name": "Extras",
      "image": null,
      "name_ar": "جبن",
      "name_en": "Cheese",
      "price": "120.00",
      "is_active": true
    }
  ]
}
```

Product addition fields:

- Writable: `classification_id`, `image`, `name_ar`, `name_en`, `price`, `is_active`
- Response: `id`, nested `classification`, `products` as product ID list, `image`, names, `price`, `is_active`

## 7. Offers

Endpoints:

| Endpoint | Methods | Permission |
|---|---:|---|
| `/api/v1/offers/` | GET | admin gets admin shape; client gets visible home shape |
| `/api/v1/offers/` | POST | admin |
| `/api/v1/offers/{offer_id}/` | GET | admin/client |
| `/api/v1/offers/{offer_id}/` | PATCH, DELETE | admin |

Current offer model choices:

- `type`: `package`, `flash`, `discount`, `announcement`, `delivery`
- `status`: `active`, `inactive`, `expired`

Current admin offer fields:

- `id`
- `market_id`, nested `market`
- `show_in_general`
- `service_city_ids`, nested `service_cities`
- `product_ids`, nested `products`
- `title`, `description`, `image`
- `type`, `discount`, `start_time`, `end_time`
- `active_days`, `use_limits`, `user_limit`
- `status`, `created_at`, `updated_at`

Important contract difference:

- There is no `scope` field and no singular `service_city_id` field in the current offer serializer.
- Offer targeting is represented by `show_in_general` and `service_city_ids`.

Validation rules:

- `end_time` must be after `start_time`.
- `discount` cannot be negative.
- `product_ids` must be a non-empty list for create.
- If `show_in_general=false`, at least one `service_city_ids` entry is required.
- If `show_in_general=true`, `market.scope` must be `general`.
- All selected service cities must be active and served by the selected market.
- All selected products must belong to the selected market.

Captured service-city offer JSON:

```json
{
  "market_id": 2,
  "show_in_general": false,
  "service_city_ids": [1],
  "product_ids": [1],
  "title": "API Lunch Offer",
  "description": "Discount",
  "type": "discount",
  "discount": "10.00",
  "start_time": "2026-07-08T09:37:43.158755+00:00",
  "end_time": "2026-07-09T10:37:43.158755+00:00",
  "active_days": ["saturday", "sunday"],
  "use_limits": 100,
  "user_limit": 2,
  "status": "active"
}
```

Captured offer response excerpt:

```json
{
  "id": 1,
  "market_id": 2,
  "show_in_general": false,
  "service_city_ids": [1],
  "product_ids": [1],
  "title": "API Lunch Offer",
  "image": null,
  "type": "discount",
  "discount": "10.00",
  "active_days": ["saturday", "sunday"],
  "status": "active",
  "products": [{"id": 1, "market_id": 2, "category_id": 1, "name": "API Burger"}],
  "service_cities": [{"id": 1, "name": "API City", "delivery_price": "120.00", "is_active": true}]
}
```

Captured multipart offer image upload:

```json
{
  "market_id": 2,
  "show_in_general": "false",
  "service_city_ids": "[1]",
  "product_ids": "[1]",
  "title": "API Image Offer",
  "description": "Image offer",
  "type": "flash",
  "discount": "5.00",
  "start_time": "<ISO datetime>",
  "end_time": "<ISO datetime>",
  "active_days": "[\"monday\",\"tuesday\"]",
  "status": "active",
  "image": "offer.gif"
}
```

Multipart list rules:

- `service_city_ids`: JSON list string such as `"[1,2]"` or repeated form fields.
- `product_ids`: JSON list string such as `"[1]"` or repeated form fields.
- `active_days`: JSON list string such as `"[\"monday\",\"tuesday\"]"`.
- `image`: file part.

Bug/contract gap found:

- Order preview/create serializers do not check offer `status`, `start_time`, or `end_time`; they validate scope/city/product compatibility only. Expired/inactive offer rejection is not enforced in the inspected order serializers.

## 8. Orders

### Current Architecture

Verified current behavior:

- One parent `Order` can contain multiple `OrderMarketSection` rows.
- `market_sections` are the real multi-market source.
- `order.market` is compatibility/first-market only.
- One admin review notification is created per parent order by `create_new_order_review_notification(order)` using `get_or_create`.
- One courier assignment is stored on the parent order.
- `/api/v1/orders/create/` returns a one-item list for client compatibility.
- Admin create uses `POST /api/v1/orders/`.
- Dashboard admin create must not use `/api/v1/orders/create/`.
- Dashboard admin create must not use `/api/v1/orders/preview/`.

Important implementation mismatch:

- `OrderListCreateView.get_serializer_class()` says POST uses `AdminOrderCreateSerializer`, but `OrderListCreateView.create()` actually normalizes request data and uses `ClientOrderCreateSerializer`.
- Therefore the live admin create contract is the normalized client-create contract plus required admin `user_id`, not the full unused `AdminOrderCreateSerializer` contract.

### Admin Order Endpoints

| Endpoint | Methods | Permission | Notes |
|---|---:|---|---|
| `/api/v1/orders/` | GET | admin | query `status` optional |
| `/api/v1/orders/` | POST | admin | create parent order |
| `/api/v1/orders/{order_id}/` | GET, PUT, PATCH | admin | detail/update |
| `/api/v1/orders/{order_id}/` | DELETE | admin | cancels order, does not hard delete |
| `/api/v1/orders/{order_id}/status/` | PATCH | admin | status transition |
| `/api/v1/orders/{order_id}/delivery-price/` | PATCH | admin | manual delivery price |
| `/api/v1/orders/{order_id}/assignment/` | PATCH | admin | assign/unassign representative |
| `/api/v1/admin/order-review/blocker/` | GET | admin | pending-review blocker |
| `/api/v1/admin/orders/{order_id}/approve/` | POST | admin | approve review |
| `/api/v1/admin/orders/{order_id}/reject/` | POST | admin | reject review |
| `/api/v1/admin/orders/{order_id}/service-city-representatives/` | GET | admin | eligible couriers |

Admin create live request fields:

- Required by current view/serializer:
  - `user_id` for admin users
  - `payment_method`
  - at least one valid `items[]` or `offers[]`
  - an address must be resolvable: explicit `delivery_address_id`/`address_id` or default matching address for target user
- Accepted and used:
  - `delivery_address_id` or `address_id`
  - `service_city_id`, but must match selected region/address when provided
  - `description`
  - `delivery_note`
  - `items[].variant_id`
  - `items[].quantity`
  - `offers[].offer_id`
- Accepted but ignored by live admin create normalization:
  - `market_id`
  - `items[].unit_price`
  - `offers[].discount_amount`
- Rejected system-controlled create fields:
  - `assigned_representative_id`, `assigned_at`, `delivered_at`, `delivery_area_id`, `delivery_type`, `delivery_price`, `order_scope`, `discount`, `subtotal_price`, `total_price`, `image`, `delivery_proof`, `status`, `review_status`, `approved_by`, `approved_at`, `rejected_by`, `rejected_at`, `rejection_reason`

Captured admin single-market create:

```json
{
  "request": {
    "user_id": 2,
    "delivery_address_id": 1,
    "market_id": 2,
    "service_city_id": 1,
    "payment_method": "cash",
    "description": "Admin description",
    "delivery_note": "Admin delivery note",
    "items": [{"variant_id": 1, "quantity": 2, "unit_price": "999.00"}],
    "offers": [{"offer_id": 1, "discount_amount": "10.00"}]
  },
  "response": {
    "id": 1,
    "market_id": 2,
    "order_scope": "service_city",
    "delivery_type": "fixed_area",
    "payment_method": "cash",
    "status": "pending",
    "review_status": "pending_review",
    "subtotal_price": "1200.00",
    "discount": "120.00",
    "delivery_price": "120.00",
    "total_price": "1200.00",
    "market_count": 1,
    "is_multi_market": false,
    "items": [{"variant_id": 1, "quantity": 2, "unit_price": "600.00"}],
    "offers": [{"offer_id": 1, "discount_amount": "120.00"}]
  }
}
```

Note: request `unit_price` was `"999.00"` but response `unit_price` was `"600.00"` from the current variant price. Request `discount_amount` was `"10.00"` but response discount was computed by backend from offer percent.

Captured admin multi-market create:

```json
{
  "request": {
    "user_id": 2,
    "delivery_address_id": 1,
    "market_id": 2,
    "service_city_id": 1,
    "payment_method": "cash",
    "items": [
      {"variant_id": 1, "quantity": 1, "unit_price": "1.00"},
      {"variant_id": 2, "quantity": 1, "unit_price": "1.00"}
    ],
    "offers": []
  },
  "response": {
    "id": 2,
    "market_id": 2,
    "subtotal_price": "1300.00",
    "delivery_price": "120.00",
    "total_price": "1420.00",
    "is_multi_market": true,
    "market_count": 2,
    "market_names_summary": "API Service Market, API Second Market",
    "market_sections": [
      {"market_id": 2, "subtotal_price": "600.00", "items": [{"variant_id": 1, "unit_price": "600.00"}]},
      {"market_id": 3, "subtotal_price": "700.00", "items": [{"variant_id": 2, "unit_price": "700.00"}]}
    ],
    "pickup_stops": [
      {"market_id": 2, "pickup_status": "pending", "sort_order": 0},
      {"market_id": 3, "pickup_status": "pending", "sort_order": 1}
    ]
  }
}
```

Admin create verification results:

- `payment_method`: required. Missing error: `{"payment_method": ["This field is required."]}`.
- `delivery_address_id`: not strictly required if the target user has a matching default address. Without any matching address, error:

```json
{
  "requires_address_selection": ["True"],
  "address_id": ["Choose an address for the currently selected market region."]
}
```

- `market_id`: not required by live create; omitted request succeeded.
- `unit_price`: not required by live create; omitted request succeeded. If present, backend ignores it and uses current `variant.price`.
- Offer-only admin orders are currently allowed if the offer has products with variants; backend adds the first variant for offer products.
- Multiple markets are inferred from variant/offer product markets.

### Client Checkout Endpoints

| Endpoint | Methods | Permission |
|---|---:|---|
| `/api/v1/orders/my/` | GET | client |
| `/api/v1/orders/preview/` | POST | authenticated; admin can preview with `user_id` by code |
| `/api/v1/orders/create/` | POST | client |

Client create request:

```json
{
  "address_id": 1,
  "payment_method": "cash",
  "description": "Client desc",
  "delivery_note": "Client note",
  "items": [{"variant_id": 1, "quantity": 1}],
  "offers": [{"offer_id": 1}]
}
```

Captured client create response shape:

```json
[
  {
    "id": 6,
    "user_id": 2,
    "delivery_address_id": 1,
    "market_id": 2,
    "order_scope": "service_city",
    "payment_method": "cash",
    "status": "pending",
    "review_status": "pending_review",
    "subtotal_price": "600.00",
    "discount": "60.00",
    "delivery_price": "120.00",
    "total_price": "660.00",
    "market_sections": [],
    "pickup_stops": [],
    "items": [],
    "offers": []
  }
]
```

The captured response is a one-item list. Arrays in the excerpt are abbreviated here; the live response included full `market_sections`, `pickup_stops`, `items`, and `offers` with the same shape as admin detail.

Preview endpoint:

- Intended use: checkout preview for a selected customer/region.
- Code permission is not client-only: admin can call it if `user_id` is supplied.
- It requires the target user to have selected a market region.
- Dashboard admin create should not call preview; use `POST /api/v1/orders/`.

Captured preview region-selection error:

```json
{
  "requires_region_selection": ["True"],
  "message": ["Select a market browsing region before checkout."],
  "current_selection": ["None"]
}
```

### Order Response Shape

Admin order detail fields:

- `id`
- `user_id`
- `customer`
- `delivery_address_id`
- `delivery_address`
- `assigned_representative_id`
- `assigned_representative`
- `market_id`
- `market`
- `order_scope`
- `service_city_id`
- `service_city`
- `delivery_area_id`
- `delivery_area`
- `delivery_type`
- `payment_method`
- `discount`
- `description`
- `status`
- `review_status`
- `delivery_price`
- `subtotal_price`
- `total_price`
- `image`
- `assigned_at`
- `delivered_at`
- `delivery_note`
- `delivery_proof`
- `approved_by`
- `approved_at`
- `rejected_by`
- `rejected_at`
- `rejection_reason`
- `is_multi_market`
- `market_count`
- `market_names_summary`
- `market_sections`
- `grouped_items`
- `grouped_offers`
- `pickup_stops`
- `history`
- `allowed_statuses`
- `items`
- `offers`
- `created_at`
- `updated_at`

Compatibility notes:

- `order.market` / `market_id` can be only the first market.
- Use `market_sections` for multi-market display and pickup grouping.
- Flat `items` / `offers` are compatibility fields.
- `grouped_items` / `grouped_offers` are preferred for grouped UI if present.

Captured order detail multi-market excerpt:

```json
{
  "id": 2,
  "market_id": 2,
  "order_scope": "service_city",
  "delivery_type": "fixed_area",
  "status": "pending",
  "review_status": "pending_review",
  "delivery_price": "120.00",
  "subtotal_price": "1300.00",
  "total_price": "1420.00",
  "is_multi_market": true,
  "market_count": 2,
  "market_names_summary": "API Service Market, API Second Market",
  "market_sections": [
    {
      "market_id": 2,
      "market": {"id": 2, "name": "API Service Market", "branch": "Central", "status": "active"},
      "subtotal_price": "600.00",
      "pickup_status": "pending",
      "items": [{"variant_id": 1, "product_name": "API Burger", "unit_price": "600.00"}]
    },
    {
      "market_id": 3,
      "market": {"id": 3, "name": "API Second Market", "branch": "Central", "status": "active"},
      "subtotal_price": "700.00",
      "pickup_status": "pending",
      "items": [{"variant_id": 2, "product_name": "API Pizza", "unit_price": "700.00"}]
    }
  ],
  "pickup_stops": [
    {"market_id": 2, "pickup_status": "pending", "sort_order": 0},
    {"market_id": 3, "pickup_status": "pending", "sort_order": 1}
  ]
}
```

### Order Choices

From models/serializers:

- `Order.status`: `pending`, `confirmed`, `under_preparation`, `ready`, `picked_up`, `on_the_way`, `delivered`, `failed_delivery`, `cancelled`
- `Order.review_status`: `pending_review`, `approved`, `rejected`
- `Order.delivery_type`: `fixed_area`, `delivery`
- `Order.order_scope`: `general`, `service_city`
- `OrderMarketSection.pickup_status`: `pending`, `picked_up`
- `OrderEvent.event_type`: `order_created`, `review_approved`, `review_rejected`, `status_changed`, `assigned`, `unassigned`, `delivery_price_changed`, `cancelled`
- `payment_method`: plain nonblank string accepted; dashboard currently sends `cash` or `cash_on_delivery` in tests/examples.

Admin status transitions:

- Before approval: only `cancelled` is allowed.
- After approval:
  - `pending` -> `confirmed`, `cancelled`
  - `confirmed` -> `under_preparation`, `cancelled`
  - `under_preparation` -> `ready` only if assigned, plus `cancelled`
  - `ready` -> `picked_up`, `cancelled`
  - `picked_up` -> `on_the_way`, `cancelled`
  - `on_the_way` -> `delivered`, `failed_delivery`, `cancelled`

Courier status transitions:

- `ready` -> `picked_up`
- `picked_up` -> `on_the_way`
- `on_the_way` -> `delivered` or `failed_delivery`

### Multi-Market Rules

Verified in code/tests:

- General cart cannot contain service-city markets.
- Service-city cart cannot contain general-only/non-serving markets.
- Service-city cart cannot mix markets from different selected city visibility.
- General order delivery destination text does not convert it to service-city.
- General orders use manual delivery:
  - `service_city = null`
  - `delivery_area = null`
  - `delivery_type = "delivery"`
  - `delivery_price = null`
- Service-city fixed area uses delivery area price once per parent order.
- Service-city unsupported/manual area uses `delivery_type="delivery"` and `delivery_price=null`.
- Delivery price is applied once per parent order, not once per market.
- Courier `picked_up` currently marks all parent order market sections as `picked_up` together. No separate pickup-section endpoint exists.

Captured Arabic scope mismatch error:

```json
{
  "items": ["لا يمكن دمج محلات عامة مع محلات مدينة في نفس الطلب"]
}
```

## 9. Notifications

Endpoints:

| Endpoint | Methods | Permission | Query params |
|---|---:|---|---|
| `/api/v1/notifications/` | GET | authenticated | `unread`, `type`, `audience`, `is_blocking`, `is_resolved` |
| `/api/v1/notifications/unread-count/` | GET | authenticated | none |
| `/api/v1/notifications/{notification_id}/read/` | PATCH | authenticated visible notification | none |
| `/api/v1/notifications/mark-all-read/` | POST | authenticated | none |
| `/api/v1/notifications/clear-read/` | DELETE | authenticated | none |
| `/api/v1/notifications/{notification_id}/` | DELETE | authenticated visible notification | none |
| `/api/v1/admin/order-review/blocker/` | GET | admin | none |

Notification choices:

- `audience`: `admin`, `courier`, `client`
- `type`: `new_order_review`, `order_assigned`, `order_rejected`

Notification payload:

```json
{
  "id": 6,
  "audience": "admin",
  "type": "new_order_review",
  "title": "New order requires review",
  "message": "Order #6 requires admin review.",
  "order_id": 6,
  "is_read": false,
  "is_blocking": true,
  "is_resolved": false,
  "read_at": null,
  "resolved_at": null,
  "created_at": "2026-07-08T10:37:43.489136Z"
}
```

Visibility:

- Admin users see notifications with `audience=admin`.
- Representatives see `audience=courier` notifications where `recipient` is the user.
- Clients see `audience=client` notifications where `recipient` is the user.

Captured unread count:

```json
{"unread_count": 6}
```

Captured review blocker shape:

```json
{
  "blocked": true,
  "pending_count": 6,
  "orders": [
    {
      "id": 6,
      "review_status": "pending_review",
      "status": "pending",
      "market_sections": [],
      "pickup_stops": []
    }
  ]
}
```

The live response includes full `OrderSerializer` objects in `orders`; the order object above is abbreviated to show the shape.

One-notification-per-parent-order behavior:

- `create_new_order_review_notification(order)` uses `Notification.objects.get_or_create(...)` for unresolved admin blocking review notification per parent order.

Delete rule:

- Unresolved blocking notifications cannot be deleted:

```json
{"detail": "Unresolved blocking notifications cannot be deleted."}
```

## 10. Couriers / Representatives

Endpoints:

| Endpoint | Methods | Permission |
|---|---:|---|
| `/api/v1/auth/representatives/` | GET | admin |
| `/api/v1/admin/orders/{order_id}/service-city-representatives/` | GET | admin |
| `/api/v1/orders/{order_id}/assignment/` | PATCH | admin |
| `/api/v1/courier/orders/` | GET | representative |
| `/api/v1/courier/orders/{order_id}/` | GET | assigned representative |
| `/api/v1/courier/orders/{order_id}/status/` | PATCH | assigned representative |

Assignment request:

```json
{"representative_id": 3}
```

Use `{"representative_id": null}` to unassign.

Assignment rules:

- Order must be approved before assignment.
- Representative must have a courier profile.
- For service-city orders, courier profile `service_city` must match the order service city.
- For general orders, any active available representative profile is eligible.
- Assignment sets `assigned_representative`, `assigned_at`, and status `ready`.
- Assignment creates a courier notification of type `order_assigned`.

Captured assignment response excerpt:

```json
{
  "message": "Order assigned successfully.",
  "order": {
    "id": 2,
    "status": "ready",
    "review_status": "approved",
    "assigned_representative_id": 3,
    "is_multi_market": true,
    "market_count": 2,
    "pickup_stops": [
      {"market_id": 2, "pickup_status": "pending", "sort_order": 0},
      {"market_id": 3, "pickup_status": "pending", "sort_order": 1}
    ]
  },
  "representative": {
    "representative_id": 3,
    "user_id": 3,
    "name": "api_courier",
    "phone": "+213555100003",
    "service_city_id": 1,
    "service_city": "API City"
  }
}
```

Courier order detail fields:

- `id`, `status`, `order_scope`, `service_city`, `delivery_area`, `delivery_type`, `market`, `market_count`
- `customer`, `delivery_address`, `total_price`, `delivery_price`, `created_at`, `assigned_at`
- Detail adds `market_sections`, `items`, `offers`, `subtotal_price`, `discount`, `delivery_note`, `delivery_proof`, `delivered_at`

Captured courier detail excerpt:

```json
{
  "id": 2,
  "status": "ready",
  "market_count": 2,
  "delivery_type": "fixed_area",
  "total_price": "1420.00",
  "market_sections": [
    {"market_id": 2, "pickup_status": "pending", "items": [{"product_name": "API Burger"}]},
    {"market_id": 3, "pickup_status": "pending", "items": [{"product_name": "API Pizza"}]}
  ],
  "items": [
    {"quantity": 1, "unit_price": "600.00", "product": {"id": 1, "name": "API Burger"}, "variant": {"id": 1, "sku": "BURGER-S", "price": 600.0}},
    {"quantity": 1, "unit_price": "700.00", "product": {"id": 3, "name": "API Pizza"}, "variant": {"id": 2, "sku": "PIZZA-L", "price": 700.0}}
  ],
  "offers": []
}
```

No dedicated delivery proof upload endpoint was found. `delivery_proof` exists on `Order` and admin `OrderSerializer`, but courier status update only accepts `status`.

## 11. Dashboard / Analytics

Endpoints:

| Endpoint | Methods | Permission | Query/body |
|---|---:|---|---|
| `/api/v1/dashboard/overview/` | GET | admin | query `from=YYYY-MM-DD`, `to=YYYY-MM-DD` |
| `/api/v1/dashboard/settings/` | GET | admin | none |
| `/api/v1/dashboard/settings/` | PATCH | admin | JSON or multipart |
| `/api/v1/home/login-dashboard-snapshot/` | GET | public | none |

Overview response shape:

```json
{
  "range": {"from": "2026-07-08", "to": "2026-07-08", "timezone": "UTC"},
  "currency": "EGP",
  "revenue": {"total": "0.00", "percentage": 0.0},
  "orders": {"total": 6, "completed": 0, "incomplete": 6, "completion_rate": 0.0},
  "customers": {"new": 1, "returning": 0, "return_rate": 0.0},
  "top_products": [],
  "active_orders": [
    {
      "id": 2,
      "number": "YM-20260708-000002",
      "customer": {"id": 2, "name": "api_client"},
      "total": "1420.00",
      "status": "picked_up",
      "created_at": "2026-07-08T10:37:43.293976Z",
      "market_count": 2,
      "market_names_summary": "API Service Market - Central, API Second Market - Central",
      "is_multi_market": true
    }
  ],
  "top_shops": []
}
```

Overview rules from service code:

- Revenue/top products/top shops use delivered orders only.
- Active orders include `pending`, `confirmed`, `under_preparation`, `ready`, `picked_up`, `on_the_way`.
- `orders.total/completed/incomplete` are calculated for the `to` day only.
- `top_shops` attributes multi-market section revenue to each section market.

Dashboard settings fields:

- Writable: `primary_color`, `subtle_color`, `accent_color`, `font_family`, `brand_name`, `brand_tagline`, multipart `logo`
- Read-only: `logo_url`, `updated_at`
- `font_family` choices: `Cairo`, `Tajawal`, `Alexandria`, `System`
- Color fields must be `#RRGGBB`.
- Logo extensions allowed by serializer: jpg, jpeg, png, webp; max 5 MB.

Login dashboard snapshot:

```json
{
  "todayOrders": 2,
  "availableCities": 1,
  "deliveryZones": 1
}
```

## 12. Error Handling Reference

Authentication required:

```json
{"detail": "Authentication credentials were not provided."}
```

Permission denied:

```json
{"detail": "Only admin users can manage orders."}
```

Validation error:

```json
{"payment_method": ["This field is required."]}
```

Not found examples:

```json
{"detail": "Not found."}
```

Address not found in custom address views:

```json
{"detail": "Address not found."}
```

Invalid additions type:

```json
{"additions": ["Expected a list of items but got type \"str\"."]}
```

Missing admin order payment method:

```json
{"payment_method": ["This field is required."]}
```

Missing address/default address for order:

```json
{
  "requires_address_selection": ["True"],
  "address_id": ["Choose an address for the currently selected market region."]
}
```

Wrong endpoint / preview without region:

```json
{
  "requires_region_selection": ["True"],
  "message": ["Select a market browsing region before checkout."],
  "current_selection": ["None"]
}
```

Market scope mismatch:

```json
{"items": ["لا يمكن دمج محلات عامة مع محلات مدينة في نفس الطلب"]}
```

Offer scope mismatch messages:

```json
{"offers": ["لا يمكن استخدام عرض مدينة داخل طلب عام"]}
```

```json
{"offers": ["لا يمكن استخدام عرض عام داخل طلب مدينة"]}
```

Invalid variant:

```json
{
  "items": [
    {
      "variant_id": ["Invalid pk \"999999\" - object does not exist."]
    }
  ]
}
```

Courier city mismatch:

```json
{"representative_id": "هذا المندوب لا يعمل في نفس مدينة الطلب."}
```

Image upload error captured through dashboard invalid logo:

```json
{
  "logo": [
    "Upload a valid image. The file you uploaded was either not an image or a corrupted image."
  ]
}
```

Delete blockers:

```json
{"detail": "Cannot delete product while orders are using it."}
```

```json
{"detail": "Cannot delete offer while orders are using it."}
```

```json
{"detail": "Unresolved blocking notifications cannot be deleted."}
```

Expired/inactive offer error:

- Unconfirmed as an API error. Code inspection found no order preview/create validation for offer `status`, `start_time`, or `end_time`.

## 13. Frontend Integration Notes

Admin orders:

- Use `POST /api/v1/orders/`.
- Do not use `/api/v1/orders/preview/` for dashboard create.
- Do not use `/api/v1/orders/create/` for dashboard create.
- Include `user_id`.
- Include `payment_method`.
- Include `delivery_address_id` explicitly even though current backend can fall back to a default address.
- Do not rely on `market_id` for pricing/grouping; backend infers markets from variants/offers.
- Do not rely on request `unit_price`; backend ignores it and uses `variant.price`.
- Do not rely on request offer `discount_amount`; backend computes it from offer percentage.
- Display `market_sections`, not only `order.market`.
- Treat `order.market` / `market_id` as compatibility/first-market only.

Products:

- Price comes from `variants[].price`; there is no `product.price`.
- Product additions in admin product create/update are IDs.
- In home product detail, additions are nested objects.
- Category image uses `category.image`.
- Product image uses `product.image`.
- `PATCH` with `variants` replaces variants; preserve-by-ID is not supported.
- For product multipart with image, scalar fields and repeated/list `additions` worked. Nested `variants` with multipart were not captured as working; prefer JSON create/update when writing nested variants.

Offers:

- Images are supported by the current serializer and captured with multipart.
- Use `show_in_general` and `service_city_ids`; do not send `scope` or `service_city_id`.
- `product_ids` is an array in JSON; in multipart send JSON text like `"[1,2]"` or repeated keys.
- `active_days` is a JSON array in JSON body; in multipart send JSON text.
- `announcement` and `delivery` are supported `type` values from the model.
- Validate offer status/time on the frontend if needed; backend order checkout does not currently reject expired/inactive offers.

Markets:

- General market create/update should omit `service_city_ids` and `delivery_area_ids`.
- Service-city market create/update should send `service_city_ids` and optionally `delivery_area_ids`.
- No market image field exists.

Images:

- Image fields can be `null`, `/media/...`, or full remote URL depending on storage/request context.
- Normalize image URLs in the frontend.
- Do not set multipart `Content-Type` manually.

Locations:

- `/api/v1/locations/service-cities/` is admin-only in current code.
- Authenticated non-admin users can read `/api/v1/locations/delivery-areas/?service_city_id=...`.
- Admin can read all addresses or filter `/api/v1/addresses/?user_id=...`.

## 14. Generated Request/Response Examples

All examples in this section were captured from real API calls in the temporary verification DB unless noted as abbreviated. Token strings are redacted.

### Login Response

```json
{
  "accessToken": "<JWT redacted>",
  "refreshToken": "<JWT redacted>",
  "expiresIn": 900,
  "user": {
    "id": "1",
    "username": "api_admin",
    "email": "api-admin@example.com",
    "phone": "+213555100001",
    "role": "admin",
    "has_password": true,
    "courier_profile": null
  }
}
```

### Service City List

```json
[
  {
    "id": 1,
    "name": "API City",
    "center_latitude": "36.7525000",
    "center_longitude": "3.0420000",
    "radius_km": "20.00",
    "delivery_price": "120.00",
    "is_active": true,
    "delivery_area_count": 1,
    "market_count": 0,
    "offer_count": 0
  }
]
```

### Delivery Area List

```json
[
  {
    "id": 1,
    "service_city_id": 1,
    "name": "API Central",
    "delivery_price": "120.00",
    "is_active": true
  }
]
```

### Address Responses

Fixed area:

```json
{
  "id": 1,
  "name": "Home",
  "line1": "1 API Street",
  "service_city_id": 1,
  "delivery_area_id": 1,
  "delivery_type": "fixed_area",
  "delivery_price_preview": "120.00"
}
```

Manual/general:

```json
{
  "id": 2,
  "name": "General Home",
  "line1": "Manual delivery street",
  "manual_city": "Mansoura",
  "manual_area": "University district",
  "service_city_id": null,
  "delivery_area_id": null,
  "delivery_type": "delivery",
  "delivery_price_preview": null
}
```

### Market Create

General market request/response:

```json
{
  "request": {
    "classification_id": 1,
    "name": "API General Market",
    "branch": "Main",
    "scope": "general",
    "status": "active"
  },
  "response": {
    "id": 1,
    "classification": {"id": 1, "name": "API Markets", "classification_type": "featured"},
    "name": "API General Market",
    "branch": "Main",
    "scope": "general",
    "status": "active",
    "service_cities": [],
    "delivery_areas": [],
    "created_at": "2026-07-08T10:37:42.963173Z",
    "updated_at": "2026-07-08T10:37:42.963205Z"
  }
}
```

Service-city market request/response:

```json
{
  "request": {
    "classification_id": 1,
    "name": "API Service Market",
    "branch": "Central",
    "scope": "service_city",
    "status": "active",
    "service_city_ids": [1],
    "delivery_area_ids": [1]
  },
  "response": {
    "id": 2,
    "classification": {"id": 1, "name": "API Markets", "classification_type": "featured"},
    "name": "API Service Market",
    "branch": "Central",
    "scope": "service_city",
    "status": "active",
    "service_cities": [{"id": 1, "name": "API City", "delivery_price": "120.00", "is_active": true}],
    "delivery_areas": [{"id": 1, "service_city_id": 1, "name": "API Central", "delivery_price": "120.00", "is_active": true}],
    "created_at": "2026-07-08T10:37:42.973831Z",
    "updated_at": "2026-07-08T10:37:42.973861Z"
  }
}
```

### Product Category Create

JSON request/response:

```json
{
  "request": {
    "classification_id": 1,
    "name": "API Meals",
    "type": "food",
    "description": "Meals category"
  },
  "response": {
    "id": 1,
    "classification": {"id": 1, "name": "API Categories"},
    "name": "API Meals",
    "type": "food",
    "description": "Meals category",
    "image": null
  }
}
```

Multipart request/response:

```json
{
  "request": {
    "classification_id": 1,
    "name": "API Drinks",
    "type": "drink",
    "description": "Drinks category",
    "image": "category.gif"
  },
  "response": {
    "id": 2,
    "classification": {"id": 1, "name": "API Categories"},
    "name": "API Drinks",
    "type": "drink",
    "description": "Drinks category",
    "image": "/media/categories/category.gif"
  }
}
```

### Product Create JSON Without Image

```json
{
  "request": {
    "market_id": 2,
    "category_id": 1,
    "is_available": true,
    "name": "API Burger",
    "description": "Burger description",
    "discount": "5.00",
    "additions": [1],
    "attribute_values": [{"attribute_id": 1, "option_id": 1}],
    "variants": [
      {
        "price": "600.00",
        "sku": "BURGER-S",
        "attribute_values": [{"attribute_id": 1, "option_id": 1}]
      }
    ]
  },
  "response": {
    "id": 1,
    "market": {"id": 2, "name": "API Service Market", "branch": "Central", "status": "active", "classification_id": 1},
    "category": {"id": 1, "name": "API Meals", "type": "food", "description": "Meals category", "image": null},
    "is_available": true,
    "name": "API Burger",
    "description": "Burger description",
    "image": null,
    "discount": "5.00",
    "attribute_values": [{"id": 1, "option": {"id": 1, "value": "Small"}}],
    "variants": [{"id": 1, "price": "600.00", "sku": "BURGER-S"}],
    "additions": [1],
    "created_at": "2026-07-08T10:37:43.096314Z",
    "updated_at": "2026-07-08T10:37:43.096344Z"
  }
}
```

### Product Create Multipart With Image

```json
{
  "request": {
    "market_id": 2,
    "category_id": 1,
    "is_available": "true",
    "name": "API Product Image",
    "description": "Image product",
    "discount": "0.00",
    "additions": [1],
    "image": "product.gif"
  },
  "response": {
    "id": 2,
    "image": "/media/products/product.gif",
    "attribute_values": [],
    "variants": [],
    "additions": [1],
    "created_at": "2026-07-08T10:37:43.122595Z",
    "updated_at": "2026-07-08T10:37:43.122625Z"
  }
}
```

### Product Detail With Variants/Additions

```json
{
  "id": 1,
  "name": "API Burger",
  "variants": [
    {
      "id": 1,
      "price": "600.00",
      "sku": "BURGER-S",
      "attribute_values": [{"attribute_id": 1, "attribute_name": "Size", "option_id": 1, "option_value": "Small"}]
    }
  ],
  "additions": [
    {
      "id": 1,
      "classification_name": "Extras",
      "name_ar": "جبن",
      "name_en": "Cheese",
      "price": "120.00",
      "is_active": true
    }
  ]
}
```

### Offer Create JSON

```json
{
  "request": {
    "market_id": 2,
    "show_in_general": false,
    "service_city_ids": [1],
    "product_ids": [1],
    "title": "API Lunch Offer",
    "description": "Discount",
    "type": "discount",
    "discount": "10.00",
    "start_time": "2026-07-08T09:37:43.158755+00:00",
    "end_time": "2026-07-09T10:37:43.158755+00:00",
    "active_days": ["saturday", "sunday"],
    "use_limits": 100,
    "user_limit": 2,
    "status": "active"
  },
  "response": {
    "id": 1,
    "market_id": 2,
    "market": {"id": 2, "name": "API Service Market", "scope": "service_city", "status": "active"},
    "show_in_general": false,
    "service_city_ids": [1],
    "service_cities": [{"id": 1, "name": "API City", "delivery_price": "120.00", "is_active": true}],
    "product_ids": [1],
    "products": [{"id": 1, "market_id": 2, "category_id": 1, "name": "API Burger"}],
    "title": "API Lunch Offer",
    "description": "Discount",
    "image": null,
    "type": "discount",
    "discount": "10.00",
    "start_time": "2026-07-08T09:37:43.158755Z",
    "end_time": "2026-07-09T10:37:43.158755Z",
    "active_days": ["saturday", "sunday"],
    "use_limits": 100,
    "user_limit": 2,
    "status": "active",
    "created_at": "2026-07-08T10:37:43.169230Z",
    "updated_at": "2026-07-08T10:37:43.169265Z"
  }
}
```

### Offer Multipart With Image

```json
{
  "request": {
    "market_id": 2,
    "show_in_general": "false",
    "service_city_ids": "[1]",
    "product_ids": "[1]",
    "title": "API Image Offer",
    "description": "Image offer",
    "type": "flash",
    "discount": "5.00",
    "start_time": "<captured ISO datetime>",
    "end_time": "<captured ISO datetime>",
    "active_days": "[\"monday\",\"tuesday\"]",
    "status": "active",
    "image": "offer.gif"
  },
  "response": {
    "id": 2,
    "market_id": 2,
    "show_in_general": false,
    "service_city_ids": [1],
    "product_ids": [1],
    "title": "API Image Offer",
    "description": "Image offer",
    "image": "/media/offers/offer.gif",
    "type": "flash",
    "discount": "5.00",
    "active_days": ["monday", "tuesday"],
    "status": "active",
    "products": [{"id": 1, "market_id": 2, "category_id": 1, "name": "API Burger"}],
    "service_cities": [{"id": 1, "name": "API City", "delivery_price": "120.00", "is_active": true}]
  }
}
```

### Admin Order Create Single-Market

```json
{
  "request": {
    "user_id": 2,
    "delivery_address_id": 1,
    "market_id": 2,
    "service_city_id": 1,
    "payment_method": "cash",
    "description": "Admin description",
    "delivery_note": "Admin delivery note",
    "items": [{"variant_id": 1, "quantity": 2, "unit_price": "999.00"}],
    "offers": [{"offer_id": 1, "discount_amount": "10.00"}]
  },
  "response": {
    "id": 1,
    "market_id": 2,
    "order_scope": "service_city",
    "delivery_type": "fixed_area",
    "payment_method": "cash",
    "discount": "120.00",
    "subtotal_price": "1200.00",
    "delivery_price": "120.00",
    "total_price": "1200.00",
    "is_multi_market": false,
    "market_count": 1,
    "market_sections": [{"market_id": 2, "subtotal_price": "1200.00", "items": [{"variant_id": 1, "quantity": 2, "unit_price": "600.00"}]}],
    "pickup_stops": [{"market_id": 2, "pickup_status": "pending", "sort_order": 0}]
  }
}
```

The request `unit_price` and `discount_amount` are accepted but ignored by live admin create; backend used variant price `"600.00"` and computed offer discount `"120.00"`.

### Admin Order Create Multi-Market

```json
{
  "request": {
    "user_id": 2,
    "delivery_address_id": 1,
    "market_id": 2,
    "service_city_id": 1,
    "payment_method": "cash",
    "description": "Admin multi",
    "delivery_note": "Two pickups",
    "items": [
      {"variant_id": 1, "quantity": 1, "unit_price": "1.00"},
      {"variant_id": 2, "quantity": 1, "unit_price": "1.00"}
    ],
    "offers": []
  },
  "response": {
    "id": 2,
    "market_id": 2,
    "order_scope": "service_city",
    "subtotal_price": "1300.00",
    "delivery_price": "120.00",
    "total_price": "1420.00",
    "is_multi_market": true,
    "market_count": 2,
    "market_names_summary": "API Service Market, API Second Market",
    "market_sections": [
      {"market_id": 2, "subtotal_price": "600.00", "items": [{"variant_id": 1, "unit_price": "600.00"}]},
      {"market_id": 3, "subtotal_price": "700.00", "items": [{"variant_id": 2, "unit_price": "700.00"}]}
    ],
    "pickup_stops": [
      {"market_id": 2, "pickup_status": "pending", "sort_order": 0},
      {"market_id": 3, "pickup_status": "pending", "sort_order": 1}
    ]
  }
}
```

### Client Order Create

```json
{
  "request": {
    "address_id": 1,
    "payment_method": "cash",
    "description": "Client desc",
    "delivery_note": "Client note",
    "items": [{"variant_id": 1, "quantity": 1}],
    "offers": [{"offer_id": 1}]
  },
  "response": [
    {
      "id": 6,
      "market_id": 2,
      "order_scope": "service_city",
      "delivery_type": "fixed_area",
      "payment_method": "cash",
      "discount": "60.00",
      "subtotal_price": "600.00",
      "delivery_price": "120.00",
      "total_price": "660.00",
      "is_multi_market": false,
      "market_count": 1,
      "market_sections": [{"market_id": 2, "subtotal_price": "600.00", "items": [{"variant_id": 1, "quantity": 1, "unit_price": "600.00"}]}],
      "pickup_stops": [{"market_id": 2, "pickup_status": "pending", "sort_order": 0}]
    }
  ]
}
```

Response is a one-item list.

### Client Preview Region Error

```json
{
  "requires_region_selection": ["True"],
  "message": ["Select a market browsing region before checkout."],
  "current_selection": ["None"]
}
```

### Notification Blocker Response

```json
{
  "blocked": true,
  "pending_count": 6,
  "orders": [
    {
      "id": 6,
      "review_status": "pending_review",
      "status": "pending",
      "market_id": 2,
      "market_count": 1,
      "is_multi_market": false,
      "market_sections": [{"market_id": 2, "pickup_status": "pending"}],
      "pickup_stops": [{"market_id": 2, "pickup_status": "pending", "sort_order": 0}]
    }
  ]
}
```

### Courier Order Detail With Pickup Sections

```json
{
  "id": 2,
  "status": "ready",
  "market_count": 2,
  "market_sections": [
    {"market_id": 2, "pickup_status": "pending", "items": [{"product_name": "API Burger"}]},
    {"market_id": 3, "pickup_status": "pending", "items": [{"product_name": "API Pizza"}]}
  ],
  "items": [
    {"quantity": 1, "unit_price": "600.00", "product": {"id": 1, "name": "API Burger"}},
    {"quantity": 1, "unit_price": "700.00", "product": {"id": 3, "name": "API Pizza"}}
  ]
}
```

## Unconfirmed Items

- Product multipart create/update with nested `variants` was not captured as working. JSON create/update with nested variants was captured and should be used for variant writes.
- Expired/inactive offer rejection is unconfirmed as an API error. Code inspection found order preview/create validates offer scope/product compatibility but not `status`, `start_time`, or `end_time`.
- No dedicated courier delivery-proof upload endpoint was found. `delivery_proof` exists on `Order` and admin `OrderSerializer`, but courier status update only accepts `status`.
- No dedicated pickup-section status endpoint was found. Courier `picked_up` marks all parent order market sections as picked up together.

## Contract Mismatches / Bugs Found

1. `POST /api/v1/orders/` advertises `AdminOrderCreateSerializer` via `get_serializer_class()`, but the create method uses `ClientOrderCreateSerializer` after normalization. This makes `market_id`, `unit_price`, and `discount_amount` accepted-but-ignored compatibility fields in live admin create.
2. `delivery_address_id` is not strictly required on admin create if the target user has a matching default address, despite the apparent admin serializer requiring it.
3. Offer-only admin orders are currently allowed by the live create path, despite the unused admin serializer requiring `items`.
4. Order create/preview does not validate offer `status`, `start_time`, or `end_time`; expired/inactive offers may be accepted if scope/product checks pass.
5. There is no dedicated courier delivery-proof upload endpoint, although `delivery_proof` exists on the `Order` model/serializer.
6. General market serializer does not enforce clearing `service_city_ids` / `delivery_area_ids`; frontend should omit them.
7. `config.test_settings` inherits Cloudinary storage for uploads when `DEBUG=False`, causing upload tests to fail without Cloudinary credentials.
8. `seed_data` test expects every project model populated, but `orders.OrderEvent` remains empty.

No backend behavior was changed while generating this report.
