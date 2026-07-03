# Complete API Report

## 1. Summary

- Total endpoints found: 82 functional URL groups, about 124 unique method-level operations.
- Apps scanned: `accounts`, `locations`, `markets`, `catalog`, `offers`, `orders`, `notifications`, `dashboard`, `config`.
- URL style: explicit `path(...)`; no DRF routers found.
- Auth registers slash/no-slash aliases for most auth/account endpoints.
- Addresses are exposed under both `/api/v1/locations/addresses/` and `/api/v1/addresses/`.
- This report was generated from actual URL, view, serializer, model, and test code.

## 2. APIs by App

## 1. Auth APIs

### API: Signup

Method: `POST`  
URL: `/api/v1/auth/signup` and `/api/v1/auth/signup/`  
Auth: No auth  
View: `RegisterView`  
Serializer: `RegisterSerializer`

Request:

```json
{
  "first_name": "Ali",
  "last_name": "Hassan",
  "username": "ali",
  "email": "ali@example.com",
  "phone": "01012345678",
  "password": "Strong@123",
  "password_confirm": "Strong@123",
  "terms_accepted": true
}
```

Success:

```json
{
  "detail": "Registration OTP sent.",
  "email": "ali@example.com"
}
```

Notes: creates inactive client user and sends registration OTP. Phone accepts Egypt/Algeria formats. Password requires length, uppercase, number, special char.

### API: Verify Email

Method: `POST`  
URL: `/api/v1/auth/verify-email` and `/api/v1/auth/verify-email/`  
Auth: No auth  
View: `VerifyRegistrationOTPView`  
Serializer: `EmailOTPSerializer`

Request:

```json
{"email": "ali@example.com", "otp": "123456"}
```

Success:

```json
{
  "accessToken": "...",
  "refreshToken": "...",
  "expiresIn": 300,
  "user": {
    "id": "1",
    "first_name": "Ali",
    "last_name": "Hassan",
    "username": "ali",
    "email": "ali@example.com",
    "phone": "+201012345678",
    "role": "client",
    "has_password": true,
    "courier_profile": null
  }
}
```

Errors:

```json
{"otp": ["Invalid verification code."]}
```

### API: Resend Verification

Method: `POST`  
URL: `/api/v1/auth/resend-verification` and `/api/v1/auth/resend-verification/`  
Auth: No auth  
View: `ResendRegistrationOTPView`  
Serializer: `ForgotPasswordSerializer`

Request:

```json
{"email": "ali@example.com"}
```

Success:

```json
{"detail": "A new registration OTP has been sent."}
```

### API: Login

Method: `POST`  
URL: `/api/v1/auth/login` and `/api/v1/auth/login/`  
Auth: No auth  
View: `LoginView`  
Serializer: `LoginSerializer`

Request:

```json
{"identifier": "ali@example.com", "password": "Strong@123"}
```

Success: same token payload as verify email.

Notes: `identifier` can be email, username, or phone. `email` is also accepted.

### API: Client Login

Method: `POST`  
URL: `/api/v1/auth/login/client` and `/api/v1/auth/login/client/`  
Auth: No auth  
View: `ClientLoginView`  
Serializer: `LoginSerializer`

Notes: rejects non-client users.

### API: Representative Login

Method: `POST`  
URL: `/api/v1/auth/login/representative` and `/api/v1/auth/login/representative/`  
Auth: No auth  
View: `RepresentativeLoginView`  
Serializer: `LoginSerializer`

Notes: courier users are stored as `role=representative`.

### API: Admin Login

Method: `POST`  
URL: `/api/v1/auth/login/admin` and `/api/v1/auth/login/admin/`  
Auth: No auth  
View: `AdminLoginView`  
Serializer: `LoginSerializer`

### API: Refresh Token

Method: `POST`  
URL: `/api/v1/auth/refresh` and `/api/v1/auth/refresh/`  
Auth: No auth  
View: `RefreshTokenView`  
Serializer: `EmailTokenRefreshSerializer`

Request:

```json
{"refreshToken": "..."}
```

Success:

```json
{"accessToken": "...", "refreshToken": "..."}
```

### API: Logout

Method: `POST`  
URL: `/api/v1/auth/logout` and `/api/v1/auth/logout/`  
Auth: Any authenticated user  
View: `LogoutView`  
Serializer: `LogoutSerializer`

Request:

```json
{"refreshToken": "..."}
```

Success:

```json
{"detail": "Logout successful."}
```

### API: Forgot Password

Method: `POST`  
URL: `/api/v1/auth/forgot-password` and `/api/v1/auth/forgot-password/`  
Auth: No auth  
View: `ForgotPasswordView`  
Serializer: `ForgotPasswordSerializer`

Request:

```json
{"email": "ali@example.com"}
```

Success:

```json
{"detail": "If an active account exists, a password reset OTP has been sent."}
```

### API: Reset Password

Method: `POST`  
URL: `/api/v1/auth/reset-password` and `/api/v1/auth/reset-password/`  
Auth: No auth  
View: `ResetPasswordView`  
Serializer: `ResetPasswordSerializer`

Request:

```json
{
  "email": "ali@example.com",
  "otp": "123456",
  "password": "NewStrong@123",
  "password_confirm": "NewStrong@123"
}
```

Success:

```json
{"detail": "Password reset successfully."}
```

## 2. Account/User APIs

### API: Me

Method: `GET`, `PATCH`, `DELETE`  
URL: `/api/v1/auth/me` and `/api/v1/auth/me/`  
Auth: Any authenticated user  
View: `MeView`  
Serializer: `UserSerializer`, `UserUpdateSerializer`, `DeleteAccountSerializer`

PATCH request:

```json
{"first_name": "Ali", "username": "ali2", "phone": "01012345678"}
```

DELETE request:

```json
{"password": "Strong@123"}
```

Success:

```json
{
  "id": "1",
  "first_name": "Ali",
  "last_name": "Hassan",
  "username": "ali2",
  "email": "ali@example.com",
  "phone": "+201012345678",
  "gender": "",
  "birth_date": null,
  "avatar_url": null,
  "username_changed_at": "2026-07-03T...",
  "role": "client",
  "has_password": true,
  "courier_profile": null
}
```

Notes: DELETE soft-deletes user and blacklists outstanding tokens.

### API: Client Profile

Method: `PATCH`, `PUT`  
URL: `/api/v1/auth/client/profile` and `/api/v1/auth/client/profile/`  
Auth: Client token  
View: `ClientProfileView`  
Serializer: `UserUpdateSerializer`

Notes: same update fields as `/me`, client-only.

### API: Admin Users

Method: `GET`, `POST`  
URL: `/api/v1/auth/users` and `/api/v1/auth/users/`  
Auth: Admin token  
View: `AdminUserListCreateView`  
Serializer: `AdminUserSerializer`, `AdminUserWriteSerializer`

POST request:

```json
{
  "first_name": "Courier",
  "last_name": "One",
  "username": "courier1",
  "email": "courier@example.com",
  "phone": "01022222222",
  "password": "Strong@123",
  "role": "representative",
  "is_active": true,
  "courier_profile": {
    "vehicle_type": "bike",
    "plate_number": "ABC123",
    "service_city": 1,
    "delivery_area": 2,
    "max_active_orders": 3,
    "is_available": true
  }
}
```

Success includes admin fields:

```json
{
  "id": "2",
  "username": "courier1",
  "role": "representative",
  "is_active": true,
  "is_staff": false,
  "is_superuser": false,
  "courier_profile": {
    "vehicle_type": "bike",
    "plate_number": "ABC123",
    "delivery_area": 2,
    "delivery_area_name": "Nasr City",
    "service_city": 1,
    "service_city_name": "Cairo",
    "max_active_orders": 3,
    "is_available": true
  }
}
```

### API: Admin Representatives

Method: `GET`  
URL: `/api/v1/auth/representatives/`  
Auth: Admin token  
View: `AdminRepresentativeListView`  
Serializer: `AdminUserSerializer`

Notes: no no-slash alias found for this endpoint.

### API: Admin User Detail

Method: `GET`, `PATCH`, `DELETE`  
URL: `/api/v1/auth/users/{user_id}` and `/api/v1/auth/users/{user_id}/`  
Auth: Admin token  
View: `AdminUserDetailView`  
Serializer: `AdminUserSerializer`, `AdminUserWriteSerializer`

Notes: DELETE soft-deletes. Courier with ready assigned orders cannot be deleted/disabled.

### API: Availability Checks

Method: `GET`  
URLs:

- `/api/v1/auth/check-username?username=ali`
- `/api/v1/auth/check-email?email=ali@example.com`
- `/api/v1/auth/check-phone?phone=01012345678`

Auth: No auth  
Views: `CheckUsernameView`, `CheckEmailView`, `CheckPhoneView`

Success:

```json
{"available": true, "registered": false}
```

## 3. Market Region APIs

### API: Region Options

Method: `GET`  
URL: `/api/v1/market-region/options/`  
Auth: Any authenticated user  
View: `MarketRegionOptionsView`  
Serializer: direct response

Success:

```json
{
  "options": [
    {"mode": "general", "label": "General", "service_city": null},
    {
      "mode": "service_city",
      "label": "Cairo",
      "service_city": {
        "id": 1,
        "name": "Cairo",
        "delivery_price": "0.00",
        "is_active": true
      }
    }
  ],
  "current_selection": null
}
```

### API: My Market Region

Method: `GET`, `PATCH`  
URL: `/api/v1/market-region/me/`  
Auth: Any authenticated user  
View: `MarketRegionMeView`  
Serializer: `MarketRegionUpdateSerializer`

PATCH general:

```json
{"mode": "general"}
```

PATCH service city:

```json
{"mode": "service_city", "service_city_id": 1}
```

PATCH clear:

```json
{"mode": null}
```

Success:

```json
{
  "current_selection": {
    "mode": "service_city",
    "label": "Cairo",
    "service_city": {
      "id": 1,
      "name": "Cairo",
      "delivery_price": "0.00",
      "is_active": true
    },
    "updated_at": "2026-07-03T..."
  }
}
```

Errors: inactive city rejected; general must not include service city; service-city mode requires service city.

## 4. GPS Detection APIs

### API: Detect Market Region From GPS

Method: `POST`  
URL: `/api/v1/market-region/detect/`  
Auth: Any authenticated user  
View: `MarketRegionDetectView`  
Serializer: `MarketRegionDetectSerializer`

Request:

```json
{"latitude": 30.0444, "longitude": 31.2357}
```

Success examples:

```json
{
  "action": "same_region",
  "current_selection": {
    "mode": "service_city",
    "service_city": {"id": 1, "name": "Cairo"}
  },
  "detected_region": {
    "mode": "service_city",
    "service_city": {"id": 1, "name": "Cairo"}
  },
  "message": "You are already in your selected market region."
}
```

```json
{
  "action": "suggest_switch",
  "current_selection": {"mode": "general", "service_city": null},
  "detected_region": {
    "mode": "service_city",
    "service_city": {"id": 1, "name": "Cairo"}
  },
  "message": "It looks like you are in Cairo. Do you want to switch your market region?"
}
```

```json
{
  "action": "unsupported_location",
  "current_selection": null,
  "detected_region": null,
  "message": "Your current location is outside available service cities. Please choose a region manually."
}
```

Notes: uses active `ServiceCity` rows with `center_latitude`, `center_longitude`, `radius_km`; nearest matching city wins. It does not update saved region.

## 5. Home APIs

### API: Home

Method: `GET`  
URL: `/api/v1/home/`  
Auth: Any authenticated user  
View: `HomeView`  
Serializer: `HomeOfferSerializer`, `HomeMarketClassificationSerializer`, `HomeProductSerializer`

Success:

```json
{
  "current_selection": {"mode": "general", "label": "General", "service_city": null},
  "location": {
    "address_id": 1,
    "name": "Home",
    "latitude": "30.0000000",
    "longitude": "31.0000000"
  },
  "offers": [],
  "market_classifications": [],
  "products": []
}
```

Error when no region:

```json
{
  "requires_region_selection": true,
  "message": "Select a market browsing region before loading market content.",
  "current_selection": null
}
```

Notes: region-filtered; uses saved Market Region only, not `DeliveryArea`.

### API: Home Search

Method: `GET`  
URL: `/api/v1/home/search/?q=milk&page=1`  
Auth: Any authenticated user  
View: `ProductSearchView`  
Serializer: `HomeProductSerializer`

Success: DRF paginated response:

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "Milk",
      "description": "",
      "image": null,
      "discount": "0.00",
      "category": {"id": 1, "name": "Dairy", "type": "food"},
      "market": {"id": 1, "name": "Market", "scope": "general"},
      "variants": [{"id": 1, "price": "20.00", "sku": "MILK-1"}]
    }
  ]
}
```

Notes: searches product, category, category classification, market, market classification.

### API: Home Products

Method: `GET`  
URL: `/api/v1/home/products/`  
Auth: Client token  
View: `AddressProductListView`  
Serializer: `HomeProductSerializer`

Query params:

- `page`
- one of `order_by_name=true`, `order_by_high_price=true`, `order_by_low_price=true`, `order_by_latest=true`

Error:

```json
{"detail": "Use only one order parameter at a time."}
```

### API: Home Product Detail

Method: `GET`  
URL: `/api/v1/home/products/{product_id}/`  
Auth: Any authenticated user  
View: `ProductDetailView`  
Serializer: `ProductDetailSerializer`

Success includes product fields plus `attribute_values`, detailed variant attributes, `additions`, `created_at`, `updated_at`.

## 6. Classification APIs

### API: All Market Classifications

Method: `GET`  
URL: `/api/v1/home/classifications/`  
Auth: Any authenticated user  
View: `MarketClassificationSummaryView`  
Serializer: `MarketClassificationCountSerializer`, `StoreMarketClassificationSerializer`

Success:

```json
{
  "common_market_classifications": [
    {
      "id": 1,
      "name": "Restaurants",
      "classification_type": "featured",
      "product_count": 12
    }
  ],
  "market_classifications": [
    {
      "id": 1,
      "name": "Restaurants",
      "classification_type": "featured",
      "product_count": 12,
      "markets": [
        {
          "id": 1,
          "name": "Market",
          "branch": "Main",
          "status": "active",
          "classification_id": 1,
          "product_count": 3,
          "products": []
        }
      ]
    }
  ]
}
```

Notes: requires saved Market Region; excludes classifications without visible markets.

### API: Featured Classifications

Method: `GET`  
URL: `/api/v1/home/classifications/featured/`  
Auth: Any authenticated user  
View: `FeaturedMarketClassificationSummaryView`  
Serializer: `StoreMarketClassificationSerializer`

Success:

```json
{
  "current_selection": {"mode": "service_city", "label": "Cairo"},
  "classifications": [
    {
      "id": 1,
      "name": "Restaurants",
      "classification_type": "featured",
      "product_count": 12,
      "markets": []
    }
  ]
}
```

### API: Popular Classifications

Method: `GET`  
URL: `/api/v1/home/classifications/popular/`  
Auth: Any authenticated user  
View: `PopularMarketClassificationSummaryView`

Notes: same shape as featured, filtered to `classification_type=popular`.

### API: Normal Classifications

Method: `GET`  
URL: `/api/v1/home/classifications/normal/`  
Auth: Any authenticated user  
View: `NormalMarketClassificationSummaryView`

Notes: same shape as featured, filtered to `classification_type=normal`.

### API: Classification Markets

Method: `GET`  
URL: `/api/v1/home/classifications/{classification_id}/markets/`  
Auth: Any authenticated user  
View: `MarketClassificationMarketsView`  
Serializer: `MarketWithCommonProductsSerializer`

Success:

```json
{
  "classification": {
    "id": 1,
    "name": "Restaurants",
    "classification_type": "featured"
  },
  "markets": [
    {
      "id": 1,
      "name": "Market",
      "branch": "Main",
      "scope": "service_city",
      "status": "active",
      "classification_id": 1,
      "service_cities": [],
      "delivery_areas": [],
      "products": []
    }
  ]
}
```

## 7. Market Classification Admin APIs

### API: Admin Market Classifications

Method: `GET`, `POST`  
URL: `/api/v1/home/market-classifications/`  
Auth: Admin token  
View: `AdminMarketClassificationListCreateView`  
Serializer: `AdminMarketClassificationSerializer`

POST:

```json
{"name": "Restaurants", "classification_type": "featured"}
```

Success:

```json
{"id": 1, "name": "Restaurants", "classification_type": "featured"}
```

Notes: `classification_type` choices are `popular`, `featured`, `normal`; default is `normal`.

### API: Admin Market Classification Detail

Method: `GET`, `PATCH`, `DELETE`  
URL: `/api/v1/home/market-classifications/{classification_id}/`  
Auth: Admin token  
View: `AdminMarketClassificationDetailView`  
Serializer: `AdminMarketClassificationSerializer`

PATCH:

```json
{"classification_type": "popular"}
```

Delete errors if markets use it:

```json
{"detail": "Cannot delete market classification while markets are using it."}
```

## 8. Market APIs

### API: Admin Markets

Method: `GET`, `POST`  
URL: `/api/v1/home/markets/`  
Auth: Admin token  
View: `AdminMarketListCreateView`  
Serializer: `AdminMarketSerializer`

POST:

```json
{
  "classification_id": 1,
  "name": "Market",
  "branch": "Main",
  "scope": "service_city",
  "status": "active",
  "service_city_ids": [1],
  "delivery_area_ids": [1]
}
```

General market:

```json
{
  "classification_id": 1,
  "name": "General Market",
  "scope": "general",
  "status": "active"
}
```

Success:

```json
{
  "id": 1,
  "classification": {"id": 1, "name": "Restaurants", "classification_type": "normal"},
  "name": "Market",
  "branch": "Main",
  "scope": "service_city",
  "status": "active",
  "service_cities": [{"id": 1, "name": "Cairo"}],
  "delivery_areas": [{"id": 1, "name": "Nasr City"}]
}
```

Notes: service-city markets require at least one active service city. General markets do not.

### API: Admin Market Detail

Method: `GET`, `PATCH`, `DELETE`  
URL: `/api/v1/home/markets/{market_id}/`  
Auth: Admin token  
View: `AdminMarketDetailView`  
Serializer: `AdminMarketSerializer`

Delete errors if orders use the market.

## 9. Product APIs

### API: Catalog Products

Method: `GET`, `POST`  
URL: `/api/v1/catalog/products/`  
Auth: Admin token  
View: `ProductListCreateView`  
Serializer: `AdminProductSerializer`

POST:

```json
{
  "market_id": 1,
  "category_id": 1,
  "is_available": true,
  "name": "Burger",
  "description": "Beef burger",
  "discount": "0.00",
  "attribute_values": [{"attribute_id": 1, "option_id": 2}],
  "variants": [
    {
      "price": "100.00",
      "sku": "BURGER-1",
      "attribute_values": [{"attribute_id": 1, "option_id": 2}]
    }
  ],
  "additions": [1]
}
```

Success includes nested `market`, `category`, `attribute_values`, `variants`, `additions`, timestamps.

### API: Catalog Product Detail

Method: `GET`, `PATCH`, `DELETE`  
URL: `/api/v1/catalog/products/{product_id}/`  
Auth: Admin token  
View: `ProductDetailView`  
Serializer: `AdminProductSerializer`

Delete returns `204` with body in code:

```json
{"details": "Deleted Successfully"}
```

### API: Liked Products

Method: `GET`  
URL: `/api/v1/catalog/products/likes/`  
Auth: Client token  
View: `ProductLikeListView`  
Serializer: `LikedProductSerializer`

### API: Toggle Product Like

Method: `POST`  
URL: `/api/v1/catalog/products/{product_id}/like/`  
Auth: Client token  
View: `ProductLikeToggleView`

Success:

```json
{"product_id": 1, "liked": true}
```

### API: Unlike Product

Method: `DELETE`  
URL: `/api/v1/catalog/products/{product_id}/unlike/`  
Auth: Client token  
View: `ProductUnlikeView`

Success:

```json
{"product_id": 1, "liked": false}
```

## 10. Offer APIs

### API: Offers

Method: `GET`, `POST`  
URL: `/api/v1/offers/`  
Auth: Admin token for POST/admin list; Client token for region-filtered GET  
View: `OfferListCreateView`  
Serializer: `AdminOfferSerializer` for admin, `HomeOfferSerializer` for client

Admin POST:

```json
{
  "market_id": 1,
  "scope": "service_city",
  "service_city_id": 1,
  "product_ids": [1, 2],
  "title": "Family Offer",
  "description": "Discount bundle",
  "type": "package",
  "discount": "10.00",
  "start_time": "2026-07-03T10:00:00Z",
  "end_time": "2026-07-10T10:00:00Z",
  "active_days": ["friday"],
  "use_limits": 100,
  "user_limit": 1,
  "status": "active"
}
```

General offer:

```json
{
  "market_id": 2,
  "scope": "general",
  "service_city_id": null,
  "product_ids": [3],
  "title": "General Offer",
  "discount": "5.00",
  "start_time": "2026-07-03T10:00:00Z",
  "end_time": "2026-07-10T10:00:00Z",
  "active_days": [],
  "status": "active"
}
```

Client GET error without region:

```json
{
  "requires_region_selection": true,
  "message": "Select a market browsing region before loading market content.",
  "current_selection": null
}
```

Notes: admin can see all; client sees active, in-window offers matching saved Market Region.

### API: Offer Detail

Method: `GET`, `PATCH`, `DELETE`  
URL: `/api/v1/offers/{offer_id}/`  
Auth: Admin for PATCH/DELETE/admin detail; Client for region-filtered GET  
View: `OfferDetailView`  
Serializer: `AdminOfferSerializer` or `HomeOfferSerializer`

Notes: client gets `404` for offers outside saved region. DELETE errors if orders use offer.

## 11. Location APIs

Location APIs are split into service cities, delivery areas, and addresses.

## 12. ServiceCity APIs

### API: Service Cities

Method: `GET`, `POST`  
URL: `/api/v1/locations/service-cities/`  
Auth: Admin token  
View: `ServiceCityListCreateView`  
Serializer: `ServiceCitySerializer`

POST:

```json
{
  "name": "Cairo",
  "center_latitude": "30.0444000",
  "center_longitude": "31.2357000",
  "radius_km": "25.00",
  "delivery_price": "0.00",
  "is_active": true
}
```

Success:

```json
{
  "id": 1,
  "name": "Cairo",
  "center_latitude": "30.0444000",
  "center_longitude": "31.2357000",
  "radius_km": "25.00",
  "delivery_price": "0.00",
  "is_active": true
}
```

Notes: `delivery_price` still exists but fixed delivery pricing now uses `DeliveryArea.delivery_price`.

### API: Service City Detail

Method: `GET`, `PATCH`, `DELETE`  
URL: `/api/v1/locations/service-cities/{city_id}/`  
Auth: Admin token  
View: `ServiceCityDetailView`  
Serializer: `ServiceCitySerializer`

Errors:

```json
{"detail": "Service city cannot be deleted while its delivery areas are in use."}
```

## 13. DeliveryArea APIs

### API: Delivery Areas

Method: `GET`, `POST`  
URL: `/api/v1/locations/delivery-areas/`  
Auth: GET any authenticated user; POST admin token  
View: `DeliveryAreaListCreateView`  
Serializer: `DeliveryAreaSerializer`

Query params:

- `service_city_id=1`

POST:

```json
{
  "service_city_id": 1,
  "name": "Nasr City",
  "delivery_price": "40.00",
  "is_active": true
}
```

Success:

```json
{
  "id": 1,
  "service_city_id": 1,
  "name": "Nasr City",
  "center_latitude": null,
  "center_longitude": null,
  "radius_km": null,
  "delivery_price": "40.00",
  "is_active": true
}
```

Notes: non-admin GET returns only active areas in active cities. Admin GET can see inactive. Duplicate active area names in same city are rejected.

### API: Delivery Area Detail

Method: `GET`, `PATCH`, `DELETE`  
URL: `/api/v1/locations/delivery-areas/{area_id}/`  
Auth: GET any authenticated user; PATCH/DELETE admin token  
View: `DeliveryAreaDetailView`  
Serializer: `DeliveryAreaSerializer`

## 14. Address APIs

### API: Addresses

Method: `GET`, `POST`  
URLs:

- `/api/v1/locations/addresses/`
- `/api/v1/addresses/`

Auth: Any authenticated user  
View: `AddressListCreateView`  
Serializer: `AddressSerializer`, `AddressWriteSerializer`

Query params:

- admin only: `user_id=1`

POST fixed area:

```json
{
  "line1": "Apartment 5",
  "details": "Second floor",
  "service_city_id": 1,
  "delivery_area_id": 2,
  "isDefault": true
}
```

POST Other:

```json
{
  "line1": "Custom neighborhood",
  "details": "Near main square",
  "service_city_id": 1,
  "delivery_area_id": null,
  "isDefault": true
}
```

Success returns the user's full address list:

```json
[
  {
    "id": 1,
    "name": "Apartment 5",
    "fullName": "Apartment 5",
    "phone": "+201012345678",
    "city": "Cairo",
    "details": "Second floor",
    "service_city": {"id": 1, "name": "Cairo"},
    "service_city_id": 1,
    "delivery_area": {"id": 2, "name": "Nasr City", "delivery_price": "40.00"},
    "delivery_area_id": 2,
    "delivery_type": "fixed_area",
    "delivery_price_preview": "40.00",
    "is_default": true,
    "isDefault": true,
    "created_at": "2026-07-03T..."
  }
]
```

Notes: if `delivery_area_id` is absent/null, address becomes `delivery_type=delivery`, `delivery_area=null`, preview price `null`.

### API: Default Address

Method: `GET`  
URLs:

- `/api/v1/locations/addresses/default/`
- `/api/v1/addresses/default/`

Auth: Any authenticated user  
View: `AddressDefaultView`  
Serializer: `AddressSerializer`

Success: address object or `null`.

### API: Address Detail

Method: `PATCH`, `DELETE`  
URLs:

- `/api/v1/locations/addresses/{address_id}/`
- `/api/v1/addresses/{address_id}/`

Auth: Any authenticated user  
View: `AddressDetailView`  
Serializer: `AddressWriteSerializer`, `AddressSerializer`

Important: URL is registered, but this view has no `GET` method.

### API: Set Default Address

Method: `PATCH`  
URLs:

- `/api/v1/locations/addresses/{address_id}/default/`
- `/api/v1/addresses/{address_id}/default/`

Auth: Any authenticated user  
View: `AddressSetDefaultView`  
Serializer: `AddressSerializer`

Success: full address list.

## 15. Order APIs

### API: My Orders

Method: `GET`  
URL: `/api/v1/orders/my/?status=pending`  
Auth: Client token  
View: `ClientOrderListView`  
Serializer: `OrderSerializer`

Success: list of orders with `customer`, `market`, `service_city`, `delivery_area`, `delivery_type`, `delivery_price`, `items`, `offers`.

### API: Order Preview

Method: `POST`  
URL: `/api/v1/orders/preview/`  
Auth: Client token  
View: `OrderPreviewView`  
Serializer: `OrderPreviewSerializer`

Request:

```json
{
  "address_id": 1,
  "items": [{"variant_id": 1, "quantity": 2}],
  "offers": [{"offer_id": 1}]
}
```

General checkout may pass:

```json
{
  "service_city_id": 1,
  "items": [{"variant_id": 1, "quantity": 1}]
}
```

Success:

```json
{
  "addresses": [],
  "selected_address": {
    "id": 1,
    "service_city": {"id": 1, "name": "Cairo"},
    "delivery_area": {"id": 2, "name": "Nasr City", "delivery_price": "40.00"},
    "delivery_type": "fixed_area",
    "delivery_price_preview": "40.00"
  },
  "service_city": {"id": 1, "name": "Cairo"},
  "market_groups": [
    {
      "market": {"id": 1, "name": "Market", "branch": "Main"},
      "service_city": {"id": 1, "name": "Cairo"},
      "delivery_area": {"id": 2, "name": "Nasr City", "delivery_price": "40.00"},
      "delivery_type": "fixed_area",
      "delivery_price": "40.00",
      "delivery_message": "",
      "delivery_available": true,
      "selected_products": [],
      "selected_offers": [],
      "pricing": {
        "products_subtotal": "100.00",
        "total_offer_discounts": "0.00",
        "delivery_price": "40.00",
        "market_total": "140.00"
      }
    }
  ],
  "summary": {
    "subtotal": "100.00",
    "discount_total": "0.00",
    "delivery_total": "40.00",
    "grand_total": "140.00"
  }
}
```

Other delivery response has:

```json
{
  "delivery_type": "delivery",
  "delivery_area": null,
  "delivery_price": null,
  "delivery_message": "Delivery price is not fixed by the system and will be determined later."
}
```

Errors:

```json
{"service_city_id": "Service city is required."}
```

```json
{
  "requires_region_selection": true,
  "message": "Select a market browsing region before checkout.",
  "current_selection": null
}
```

### API: Client Create Order

Method: `POST`  
URL: `/api/v1/orders/create/`  
Auth: Client token  
View: `ClientOrderCreateView`  
Serializer: `ClientOrderCreateSerializer`

Request:

```json
{
  "address_id": 1,
  "payment_method": "cash",
  "description": "",
  "delivery_note": "Call on arrival",
  "items": [{"variant_id": 1, "quantity": 2}],
  "offers": [{"offer_id": 1}]
}
```

Success: `201`, list of created orders. One order is created per market group.

Notes: order starts `status=pending`, `review_status=pending_review`; no auto courier assignment.

### API: Admin Orders

Method: `GET`, `POST`  
URL: `/api/v1/orders/?status=pending`  
Auth: Admin token  
View: `OrderListCreateView`  
Serializer: `OrderSerializer`

POST:

```json
{
  "user_id": 1,
  "delivery_address_id": 1,
  "market_id": 1,
  "payment_method": "cash",
  "items": [{"variant_id": 1, "quantity": 1, "unit_price": "100.00"}],
  "offers": [{"offer_id": 1, "discount_amount": "10.00"}]
}
```

Notes: serializer normalizes delivery fields from address when present.

### API: Admin Order Detail

Method: `GET`, `PATCH`, `DELETE`  
URL: `/api/v1/orders/{order_id}/`  
Auth: Admin token  
View: `OrderDetailView`  
Serializer: `OrderSerializer`

Notes: DELETE cancels order and clears assignment; it does not physically delete.

### API: Admin Order Status

Method: `PATCH`  
URL: `/api/v1/orders/{order_id}/status/`  
Auth: Admin token  
View: `OrderStatusView`  
Serializer: `OrderStatusSerializer`

Request:

```json
{"status": "under_preparation"}
```

### API: Admin Order Assignment

Method: `PATCH`  
URL: `/api/v1/orders/{order_id}/assignment/`  
Auth: Admin token  
View: `OrderAssignmentView`  
Serializer: `OrderAssignmentSerializer`

Request:

```json
{"representative_id": 3}
```

Success:

```json
{
  "message": "Order assigned successfully.",
  "order": {},
  "representative": {
    "representative_id": 3,
    "user_id": 3,
    "name": "Courier One",
    "phone": "+2010...",
    "service_city_id": 1,
    "service_city": "Cairo"
  }
}
```

Errors: order must be approved; representative must have courier profile and same service city.

## 16. Admin Order Review APIs

### API: Order Review Blocker

Method: `GET`  
URL: `/api/v1/admin/order-review/blocker/`  
Auth: Admin token  
View: `AdminOrderReviewBlockerView`  
Serializer: `OrderSerializer`

Success:

```json
{"blocked": true, "pending_count": 2, "orders": []}
```

### API: Approve Order

Method: `POST`  
URL: `/api/v1/admin/orders/{order_id}/approve/`  
Auth: Admin token  
View: `AdminOrderApproveView`  
Serializer: `OrderSerializer`, `RepresentativeSummarySerializer`

Success:

```json
{
  "message": "Order approved successfully.",
  "order": {},
  "service_city": {"id": 1, "name": "Cairo"},
  "available_representatives": []
}
```

Notes: sets `review_status=approved`, `status=under_preparation`.

### API: Reject Order

Method: `POST`  
URL: `/api/v1/admin/orders/{order_id}/reject/`  
Auth: Admin token  
View: `AdminOrderRejectView`  
Serializer: `OrderReviewActionSerializer`

Request:

```json
{"rejection_reason": "Out of stock"}
```

Success:

```json
{
  "message": "Order rejected successfully.",
  "order_id": 1,
  "status": "cancelled",
  "review_status": "rejected",
  "rejection_reason": "Out of stock"
}
```

### API: Service-City Representatives For Order

Method: `GET`  
URL: `/api/v1/admin/orders/{order_id}/service-city-representatives/`  
Auth: Admin token  
View: `AdminOrderServiceCityRepresentativesView`  
Serializer: `RepresentativeSummarySerializer`

Success:

```json
{
  "order_id": 1,
  "service_city": {"id": 1, "name": "Cairo"},
  "representatives": []
}
```

## 17. Courier APIs

### API: Courier Orders

Method: `GET`  
URL: `/api/v1/courier/orders/?status=ready`  
Auth: Courier token  
View: `CourierOrderListView`  
Serializer: `CourierOrderListSerializer`

Success:

```json
[
  {
    "id": 1,
    "status": "ready",
    "service_city": {"id": 1, "name": "Cairo"},
    "delivery_area": null,
    "delivery_type": "delivery",
    "market": {"id": 1, "name": "Market", "branch": "Main", "status": "active"},
    "customer": {"id": 1, "name": "Ali", "phone": "+2010..."},
    "delivery_address": {
      "id": 1,
      "name": "Other area",
      "details": "",
      "delivery_area": null,
      "delivery_type": "delivery"
    },
    "total_price": "100.00",
    "delivery_price": null,
    "created_at": "2026-07-03T...",
    "assigned_at": "2026-07-03T..."
  }
]
```

Errors:

```json
{"status": "Unsupported status filter."}
```

### API: Courier Order Detail

Method: `GET`  
URL: `/api/v1/courier/orders/{order_id}/`  
Auth: Courier token  
View: `CourierOrderDetailView`  
Serializer: `CourierOrderDetailSerializer`

Success includes list fields plus `items`, `offers`, `subtotal_price`, `discount`, `delivery_note`, `delivery_proof`, `delivered_at`.

### API: Courier Order Status

Method: `PATCH`  
URL: `/api/v1/courier/orders/{order_id}/status/`  
Auth: Courier token  
View: `CourierOrderStatusView`  
Serializer: `CourierOrderStatusSerializer`

Request:

```json
{"status": "picked_up"}
```

Allowed transitions:

- `ready` -> `picked_up`
- `picked_up` -> `on_the_way`
- `on_the_way` -> `delivered` or `failed_delivery`

## 18. Notifications APIs

### API: Notifications

Method: `GET`  
URL: `/api/v1/notifications/`  
Auth: Any authenticated user  
View: `NotificationListView`  
Serializer: `NotificationSerializer`

Query params:

- `unread=true|false`
- `type=...`
- `audience=...`
- `is_blocking=true|false`
- `is_resolved=true|false`

Success:

```json
[
  {
    "id": 1,
    "audience": "admin",
    "type": "order_review",
    "title": "New order",
    "message": "Order needs review",
    "order_id": 1,
    "is_read": false,
    "is_blocking": true,
    "is_resolved": false,
    "created_at": "2026-07-03T..."
  }
]
```

Notes: admins see admin-audience notifications; couriers and clients see their own recipient notifications.

### API: Mark Notification Read

Method: `PATCH`  
URL: `/api/v1/notifications/{notification_id}/read/`  
Auth: Any authenticated user  
View: `NotificationReadView`  
Serializer: `NotificationSerializer`

### API: Mark All Notifications Read

Method: `POST`  
URL: `/api/v1/notifications/mark-all-read/`  
Auth: Any authenticated user  
View: `NotificationMarkAllReadView`

Success:

```json
{"marked_read": 3}
```

### API: Unread Count

Method: `GET`  
URL: `/api/v1/notifications/unread-count/`  
Auth: Any authenticated user  
View: `NotificationUnreadCountView`

Success:

```json
{"unread_count": 2}
```

## 19. Other APIs

### API: Dashboard Overview

Method: `GET`  
URL: `/api/v1/dashboard/overview/?from=2026-07-01&to=2026-07-03`  
Auth: Admin token  
View: `DashboardOverviewView`  
Serializer: `DashboardRangeQuerySerializer`, `DashboardOverviewSerializer`

Success:

```json
{
  "range": {"from": "2026-07-01", "to": "2026-07-03", "timezone": "Africa/Tripoli"},
  "currency": "EGP",
  "revenue": {"total": "1000.00", "percentage": 12.5},
  "orders": {"total": 10, "completed": 7, "incomplete": 3, "completion_rate": 70.0},
  "customers": {"new": 2, "returning": 5, "return_rate": 50.0},
  "top_products": [],
  "active_orders": [],
  "top_shops": []
}
```

Error:

```json
{"to": "The to date must be on or after the from date."}
```

## Catalog Admin APIs

These are all admin-only CRUD APIs using the listed serializers:

| API | Methods | URL | View | Serializer |
|---|---:|---|---|---|
| Addition classifications | GET, POST | `/api/v1/catalog/addition-classifications/` | `AdditionClassificationListCreateView` | `AdditionClassificationSerializer` |
| Addition classification detail | GET, PATCH, DELETE | `/api/v1/catalog/addition-classifications/{classification_id}/` | `AdditionClassificationDetailView` | `AdditionClassificationSerializer` |
| Category classifications | GET, POST | `/api/v1/catalog/category-classifications/` | `CategoryClassificationListCreateView` | `CategoryClassificationSerializer` |
| Category classification detail | GET, PATCH, DELETE | `/api/v1/catalog/category-classifications/{classification_id}/` | `CategoryClassificationDetailView` | `CategoryClassificationSerializer` |
| Product categories | GET, POST | `/api/v1/catalog/product-categories/` | `ProductCategoryListCreateView` | `ProductCategorySerializer` |
| Product category detail | GET, PATCH, DELETE | `/api/v1/catalog/product-categories/{category_id}/` | `ProductCategoryDetailView` | `ProductCategorySerializer` |
| Category attributes | GET, POST | `/api/v1/catalog/category-attributes/` | `CategoryAttributeListCreateView` | `AdminCategoryAttributeSerializer` |
| Category attribute detail | GET, PATCH, DELETE | `/api/v1/catalog/category-attributes/{attribute_id}/` | `CategoryAttributeDetailView` | `AdminCategoryAttributeSerializer` |
| Category options | GET, POST | `/api/v1/catalog/category-options/` | `CategoryOptionListCreateView` | `AdminCategoryOptionSerializer` |
| Category option detail | GET, PATCH, DELETE | `/api/v1/catalog/category-options/{option_id}/` | `CategoryOptionDetailView` | `AdminCategoryOptionSerializer` |
| Product additions | GET, POST | `/api/v1/catalog/product-additions/` | `ProductAdditionListCreateView` | `ProductAdditionSerializer` |
| Product addition detail | GET, PATCH, DELETE | `/api/v1/catalog/product-additions/{addition_id}/` | `ProductAdditionDetailView` | `ProductAdditionSerializer` |

Common create examples:

```json
{"name": "Food"}
```

```json
{"classification_id": 1, "name": "Meals", "type": "food", "description": "", "image": null}
```

```json
{"category_id": 1, "name": "Size"}
```

```json
{"attribute_id": 1, "value": "Large"}
```

```json
{
  "classification_id": 1,
  "image": null,
  "name_ar": "Cheese",
  "name_en": "Cheese",
  "price": "10.00",
  "is_active": true
}
```

Common delete protected errors:

```json
{"detail": "Cannot delete product category while products are using it."}
```

## Analysis

### A. URLs Registered But Missing From Tests

Based on string searches in test files:

- Auth slash aliases are mostly not directly tested: `/signup/`, `/login/`, `/me/`, etc.
- `/api/v1/locations/addresses/` and `/api/v1/locations/addresses/default/` appear less covered than the root alias `/api/v1/addresses/`.
- `/api/v1/addresses/{id}/default/` and `/api/v1/locations/addresses/{id}/default/` are registered; tests did not visibly reference them.
- `/api/v1/admin/orders/{order_id}/reject/` and `/api/v1/admin/orders/{order_id}/service-city-representatives/` are registered; direct test references were not visible in the search output.
- Dashboard, market-region detect, classification type endpoints, offers, catalog CRUD, service cities, delivery areas, notifications, and core order/courier flows do have visible test references.

### B. Views That Exist But Are Not Registered

- `locations.views.DeliveryAreaListView` exists as a backward-compatible read-only alias but is not registered in `locations/urls.py` or `locations/address_urls.py`.

### C. URLs Supporting POST/PATCH/DELETE But Not GET

- `POST /api/v1/auth/signup`
- `POST /api/v1/auth/verify-email`
- `POST /api/v1/auth/resend-verification`
- `POST /api/v1/auth/login*`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/forgot-password`
- `POST /api/v1/auth/reset-password`
- `PATCH/DELETE /api/v1/locations/addresses/{id}/` and `/api/v1/addresses/{id}/` have no GET implementation.
- `PATCH /api/v1/locations/addresses/{id}/default/` and `/api/v1/addresses/{id}/default/`
- `POST /api/v1/orders/preview/`
- `POST /api/v1/orders/create/`
- `PATCH /api/v1/orders/{id}/status/`
- `PATCH /api/v1/orders/{id}/assignment/`
- `POST /api/v1/admin/orders/{id}/approve/`
- `POST /api/v1/admin/orders/{id}/reject/`
- `PATCH /api/v1/courier/orders/{id}/status/`
- `PATCH /api/v1/notifications/{id}/read/`
- `POST /api/v1/notifications/mark-all-read/`
- `POST /api/v1/catalog/products/{id}/like/`
- `DELETE /api/v1/catalog/products/{id}/unlike/`

### D. Duplicate Or Conflicting URL Patterns

- `accounts/urls.py` intentionally registers no-slash and slash versions for most auth/account endpoints.
- Addresses are duplicated under both `/api/v1/locations/addresses/` and `/api/v1/addresses/`.
- No DRF router conflicts found.
- Typed classification routes are safe because `{classification_id}` uses `int`, so `featured`, `popular`, `normal` do not conflict.

### E. APIs That Require Market Region Selection

- `GET /api/v1/home/`
- `GET /api/v1/home/search/`
- `GET /api/v1/home/products/`
- `GET /api/v1/home/products/{id}/`
- `GET /api/v1/home/classifications/`
- `GET /api/v1/home/classifications/featured/`
- `GET /api/v1/home/classifications/popular/`
- `GET /api/v1/home/classifications/normal/`
- `GET /api/v1/home/classifications/{id}/markets/`
- Client `GET /api/v1/offers/`
- Client `GET /api/v1/offers/{id}/`
- `POST /api/v1/orders/preview/`
- `POST /api/v1/orders/create/`

### F. APIs Affected By DeliveryArea Pricing

- `GET/POST/PATCH/DELETE /api/v1/locations/delivery-areas/`
- Address create/update/list/default APIs
- `POST /api/v1/orders/preview/`
- `POST /api/v1/orders/create/`
- Order serializers used by `/api/v1/orders/*`, admin review responses, and courier responses

Rules in code: fixed-area address/order uses `DeliveryArea.delivery_price`; Other uses `delivery_type=delivery`, `delivery_area=null`, `delivery_price=null`.

### G. APIs Affected By GPS Detection

- Only `POST /api/v1/market-region/detect/`.
- `ServiceCity` admin APIs expose/update `center_latitude`, `center_longitude`, and `radius_km`, which detection uses.

### H. APIs Affected By `classification_type`

- Admin market classification CRUD
- `GET /api/v1/home/`
- `GET /api/v1/home/classifications/`
- `GET /api/v1/home/classifications/featured/`
- `GET /api/v1/home/classifications/popular/`
- `GET /api/v1/home/classifications/normal/`
- `GET /api/v1/home/classifications/{id}/markets/`
