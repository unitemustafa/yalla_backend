# Complete API Report

Generated from actual Django/DRF responses verified with `curl` against an isolated temporary SQLite database/server. Token values are redacted.

## Global Notes

- Base URL used for verification: `http://127.0.0.1:8765`.
- Use `Authorization: Bearer <accessToken>` for authenticated endpoints.
- Offer `type` choices: `package`, `flash`, `discount`, `announcement`, `delivery`.
- Offer `status` choices: `active`, `inactive`, `expired`.
- Order `status` choices: `pending`, `confirmed`, `under_preparation`, `ready`, `picked_up`, `on_the_way`, `delivered`, `failed_delivery`, `cancelled`.
- Order `review_status` choices: `pending_review`, `approved`, `rejected`.
- `payment_method` is a free nonblank string in the current model.

## Auth

### Admin login

Method: `POST`  
URL: `/api/v1/auth/login/admin/`  
Auth: None  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "email": "seed.admin@yalla.test",
  "password": "SeedPass1!"
}
```

Response body:

```json
{
  "accessToken": "<accessToken>",
  "refreshToken": "<refreshToken>",
  "expiresIn": 900,
  "user": {
    "id": "1",
    "first_name": "يلا",
    "last_name": "مشرف",
    "username": "seed_admin",
    "email": "seed.admin@yalla.test",
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



### Client login

Method: `POST`  
URL: `/api/v1/auth/login/client/`  
Auth: None  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "email": "seed.amina@yalla.test",
  "password": "SeedPass1!"
}
```

Response body:

```json
{
  "accessToken": "<accessToken>",
  "refreshToken": "<refreshToken>",
  "expiresIn": 900,
  "user": {
    "id": "2",
    "first_name": "أمينة",
    "last_name": "بن سالم",
    "username": "seed_amina",
    "email": "seed.amina@yalla.test",
    "phone": "+213555100002",
    "gender": "",
    "birth_date": null,
    "avatar_url": null,
    "username_changed_at": null,
    "role": "client",
    "has_password": true,
    "courier_profile": null
  }
}
```



### Representative login

Method: `POST`  
URL: `/api/v1/auth/login/representative/`  
Auth: None  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "email": "seed.courier@yalla.test",
  "password": "SeedPass1!"
}
```

Response body:

```json
{
  "accessToken": "<accessToken>",
  "refreshToken": "<refreshToken>",
  "expiresIn": 900,
  "user": {
    "id": "4",
    "first_name": "سفيان",
    "last_name": "مندوب",
    "username": "seed_courier",
    "email": "seed.courier@yalla.test",
    "phone": "+213555100004",
    "gender": "",
    "birth_date": null,
    "avatar_url": null,
    "username_changed_at": null,
    "role": "representative",
    "has_password": true,
    "courier_profile": {
      "vehicle_type": "Motorcycle",
      "plate_number": "YH-1004",
      "delivery_area": 1,
      "delivery_area_name": "وسط الجزائر",
      "service_city": 1,
      "service_city_name": "الجزائر",
      "max_active_orders": 3,
      "is_available": true
    }
  }
}
```



### Signup

Method: `POST`  
URL: `/api/v1/auth/signup/`  
Auth: None  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "first_name": "Report",
  "last_name": "User",
  "username": "report_user",
  "email": "report.user@yalla.test",
  "phone": "+213555900001",
  "password": "ReportPass1!",
  "password_confirm": "ReportPass1!",
  "terms_accepted": true
}
```

Response body:

```json
{
  "detail": "Registration OTP sent.",
  "email": "report.user@yalla.test",
  "dev_otp": "382901"
}
```



### Verify email

Method: `POST`  
URL: `/api/v1/auth/verify-email/`  
Auth: None  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "email": "report.user@yalla.test",
  "otp": "382901"
}
```

Response body:

```json
{
  "accessToken": "<accessToken>",
  "refreshToken": "<refreshToken>",
  "expiresIn": 900,
  "user": {
    "id": "10",
    "first_name": "Report",
    "last_name": "User",
    "username": "report_user",
    "email": "report.user@yalla.test",
    "phone": "+213555900001",
    "gender": "",
    "birth_date": null,
    "avatar_url": null,
    "username_changed_at": null,
    "role": "client",
    "has_password": true,
    "courier_profile": null
  }
}
```



### Resend verification

Method: `POST`  
URL: `/api/v1/auth/resend-verification/`  
Auth: None  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "email": "seed.pending@yalla.test"
}
```

Response body:

```json
{
  "detail": "A new registration OTP has been sent.",
  "dev_otp": "748912"
}
```



### Generic login

Method: `POST`  
URL: `/api/v1/auth/login/`  
Auth: None  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "email": "seed.amina@yalla.test",
  "password": "SeedPass1!"
}
```

Response body:

```json
{
  "accessToken": "<accessToken>",
  "refreshToken": "<refreshToken>",
  "expiresIn": 900,
  "user": {
    "id": "2",
    "first_name": "أمينة",
    "last_name": "بن سالم",
    "username": "seed_amina",
    "email": "seed.amina@yalla.test",
    "phone": "+213555100002",
    "gender": "",
    "birth_date": null,
    "avatar_url": null,
    "username_changed_at": null,
    "role": "client",
    "has_password": true,
    "courier_profile": null
  }
}
```



### Refresh token

Method: `POST`  
URL: `/api/v1/auth/refresh/`  
Auth: None  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "refresh": "<refresh>"
}
```

Response body:

```json
{
  "accessToken": "<accessToken>",
  "refreshToken": "<refreshToken>"
}
```



### Current user

Method: `GET`  
URL: `/api/v1/auth/me/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": "2",
  "first_name": "أمينة",
  "last_name": "بن سالم",
  "username": "seed_amina",
  "email": "seed.amina@yalla.test",
  "phone": "+213555100002",
  "gender": "",
  "birth_date": null,
  "avatar_url": null,
  "username_changed_at": null,
  "role": "client",
  "has_password": true,
  "courier_profile": null
}
```



### Update current user

Method: `PATCH`  
URL: `/api/v1/auth/me/`  
Auth: Client token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "gender": "female"
}
```

Response body:

```json
{
  "id": "2",
  "first_name": "أمينة",
  "last_name": "بن سالم",
  "username": "seed_amina",
  "email": "seed.amina@yalla.test",
  "phone": "+213555100002",
  "gender": "female",
  "birth_date": null,
  "avatar_url": null,
  "username_changed_at": null,
  "role": "client",
  "has_password": true,
  "courier_profile": null
}
```



### Client profile update

Method: `PATCH`  
URL: `/api/v1/auth/client/profile/`  
Auth: Client token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "first_name": "أمينة"
}
```

Response body:

```json
{
  "id": "2",
  "first_name": "أمينة",
  "last_name": "بن سالم",
  "username": "seed_amina",
  "email": "seed.amina@yalla.test",
  "phone": "+213555100002",
  "gender": "female",
  "birth_date": null,
  "avatar_url": null,
  "username_changed_at": null,
  "role": "client",
  "has_password": true,
  "courier_profile": null
}
```



### Client profile replace

Method: `PUT`  
URL: `/api/v1/auth/client/profile/`  
Auth: Client token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "first_name": "أمينة",
  "last_name": "بن سالم",
  "gender": "female"
}
```

Response body:

```json
{
  "id": "2",
  "first_name": "أمينة",
  "last_name": "بن سالم",
  "username": "seed_amina",
  "email": "seed.amina@yalla.test",
  "phone": "+213555100002",
  "gender": "female",
  "birth_date": null,
  "avatar_url": null,
  "username_changed_at": null,
  "role": "client",
  "has_password": true,
  "courier_profile": null
}
```



### Forgot password

Method: `POST`  
URL: `/api/v1/auth/forgot-password/`  
Auth: None  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "email": "seed.karim@yalla.test"
}
```

Response body:

```json
{
  "detail": "If an active account exists, a password reset OTP has been sent.",
  "dev_otp": "949910"
}
```



### Reset password

Method: `POST`  
URL: `/api/v1/auth/reset-password/`  
Auth: None  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "email": "seed.karim@yalla.test",
  "otp": "949910",
  "password": "ResetPass1!",
  "password_confirm": "ResetPass1!"
}
```

Response body:

```json
{
  "detail": "Password reset successfully."
}
```



### Check username

Method: `GET`  
URL: `/api/v1/auth/check-username/?username=seed_admin`  
Auth: None  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "available": false,
  "registered": true
}
```



### Check email

Method: `GET`  
URL: `/api/v1/auth/check-email/?email=seed.admin%40yalla.test`  
Auth: None  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "available": false,
  "registered": true
}
```



### Check phone

Method: `GET`  
URL: `/api/v1/auth/check-phone/?phone=%2B213555100001`  
Auth: None  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "available": false,
  "registered": true
}
```



### Login for logout

Method: `POST`  
URL: `/api/v1/auth/login/client/`  
Auth: None  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "email": "seed.amina@yalla.test",
  "password": "SeedPass1!"
}
```

Response body:

```json
{
  "accessToken": "<accessToken>",
  "refreshToken": "<refreshToken>",
  "expiresIn": 900,
  "user": {
    "id": "2",
    "first_name": "أمينة",
    "last_name": "بن سالم",
    "username": "seed_amina",
    "email": "seed.amina@yalla.test",
    "phone": "+213555100002",
    "gender": "female",
    "birth_date": null,
    "avatar_url": null,
    "username_changed_at": null,
    "role": "client",
    "has_password": true,
    "courier_profile": null
  }
}
```



### Delete current user

Method: `DELETE`  
URL: `/api/v1/auth/me/`  
Auth: Verified client token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "password": "ReportPass1!"
}
```

Response body:

```json
{
  "detail": "Account deleted."
}
```



### Logout

Method: `POST`  
URL: `/api/v1/auth/logout/`  
Auth: Client token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "refresh": "<refresh>"
}
```

Response body:

```json
{
  "detail": "Logout successful."
}
```



## Accounts

### Admin users list

Method: `GET`  
URL: `/api/v1/auth/users/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": "9",
    "first_name": "ليلى",
    "last_name": "سائقة",
    "username": "seed_courier3",
    "email": "seed.courier3@yalla.test",
    "phone": "+213555100009",
    "gender": "",
    "birth_date": null,
    "avatar_url": null,
    "username_changed_at": null,
    "role": "representative",
    "has_password": true,
    "courier_profile": {
      "vehicle_type": "Car",
      "plate_number": "YH-1009",
      "delivery_area": 5,
      "delivery_area_name": "وسط قسنطينة",
      "service_city": 3,
      "service_city_name": "قسنطينة",
      "max_active_orders": 5,
      "is_available": false
    },
    "is_active": true,
    "is_staff": false,
    "is_superuser": false,
    "created_at": "2026-07-05T07:25:39.487290Z",
    "updated_at": "2026-07-05T07:25:39.487308Z"
  },
  "... 8 more item(s)"
]
```



### Admin representatives list

Method: `GET`  
URL: `/api/v1/auth/representatives/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": "9",
    "first_name": "ليلى",
    "last_name": "سائقة",
    "username": "seed_courier3",
    "email": "seed.courier3@yalla.test",
    "phone": "+213555100009",
    "gender": "",
    "birth_date": null,
    "avatar_url": null,
    "username_changed_at": null,
    "role": "representative",
    "has_password": true,
    "courier_profile": {
      "vehicle_type": "Car",
      "plate_number": "YH-1009",
      "delivery_area": 5,
      "delivery_area_name": "وسط قسنطينة",
      "service_city": 3,
      "service_city_name": "قسنطينة",
      "max_active_orders": 5,
      "is_available": false
    },
    "is_active": true,
    "is_staff": false,
    "is_superuser": false,
    "created_at": "2026-07-05T07:25:39.487290Z",
    "updated_at": "2026-07-05T07:25:39.487308Z"
  },
  "... 2 more item(s)"
]
```



### Admin user create

Method: `POST`  
URL: `/api/v1/auth/users/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "first_name": "Doc",
  "last_name": "Client",
  "username": "doc_client",
  "email": "doc.client@yalla.test",
  "phone": "+213555900002",
  "password": "DocPass1!",
  "role": "client",
  "is_active": true
}
```

Response body:

```json
{
  "id": "11",
  "first_name": "Doc",
  "last_name": "Client",
  "username": "doc_client",
  "email": "doc.client@yalla.test",
  "phone": "+213555900002",
  "gender": "",
  "birth_date": null,
  "avatar_url": null,
  "username_changed_at": null,
  "role": "client",
  "has_password": true,
  "courier_profile": null,
  "is_active": true,
  "is_staff": false,
  "is_superuser": false,
  "created_at": "2026-07-05T07:25:54.714904Z",
  "updated_at": "2026-07-05T07:25:54.714920Z"
}
```



### Admin user detail

Method: `GET`  
URL: `/api/v1/auth/users/11/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": "11",
  "first_name": "Doc",
  "last_name": "Client",
  "username": "doc_client",
  "email": "doc.client@yalla.test",
  "phone": "+213555900002",
  "gender": "",
  "birth_date": null,
  "avatar_url": null,
  "username_changed_at": null,
  "role": "client",
  "has_password": true,
  "courier_profile": null,
  "is_active": true,
  "is_staff": false,
  "is_superuser": false,
  "created_at": "2026-07-05T07:25:54.714904Z",
  "updated_at": "2026-07-05T07:25:54.714920Z"
}
```



### Admin user update

Method: `PATCH`  
URL: `/api/v1/auth/users/11/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "first_name": "DocUpdated"
}
```

Response body:

```json
{
  "id": "11",
  "first_name": "DocUpdated",
  "last_name": "Client",
  "username": "doc_client",
  "email": "doc.client@yalla.test",
  "phone": "+213555900002",
  "gender": "",
  "birth_date": null,
  "avatar_url": null,
  "username_changed_at": null,
  "role": "client",
  "has_password": true,
  "courier_profile": null,
  "is_active": true,
  "is_staff": false,
  "is_superuser": false,
  "created_at": "2026-07-05T07:25:54.714904Z",
  "updated_at": "2026-07-05T07:25:54.778368Z"
}
```



### Admin user delete

Method: `DELETE`  
URL: `/api/v1/auth/users/11/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `204`


Request body:

```text
none
```

Response body:

```text
empty
```



## Market Region

### Set market region

Method: `PATCH`  
URL: `/api/v1/market-region/me/`  
Auth: Client token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "mode": "service_city",
  "service_city_id": 1
}
```

Response body:

```json
{
  "current_selection": {
    "mode": "service_city",
    "label": "الجزائر",
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": 250.0,
      "is_active": true
    },
    "updated_at": "2026-07-05T07:25:54.171625Z"
  }
}
```



### Market region options

Method: `GET`  
URL: `/api/v1/market-region/options/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "options": [
    {
      "mode": "general",
      "label": "General",
      "service_city": null
    },
    "... 4 more item(s)"
  ],
  "current_selection": {
    "mode": "service_city",
    "label": "الجزائر",
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": 250.0,
      "is_active": true
    },
    "updated_at": "2026-07-05T07:25:54.171625Z"
  }
}
```



### Current market region

Method: `GET`  
URL: `/api/v1/market-region/me/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "current_selection": {
    "mode": "service_city",
    "label": "الجزائر",
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": 250.0,
      "is_active": true
    },
    "updated_at": "2026-07-05T07:25:54.171625Z"
  }
}
```



### Detect market region

Method: `POST`  
URL: `/api/v1/market-region/detect/`  
Auth: Client token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "latitude": "36.7538000",
  "longitude": "3.0588000"
}
```

Response body:

```json
{
  "action": "same_region",
  "current_selection": {
    "mode": "service_city",
    "service_city": {
      "id": 1,
      "name": "الجزائر"
    }
  },
  "detected_region": {
    "mode": "service_city",
    "service_city": {
      "id": 1,
      "name": "الجزائر"
    }
  },
  "message": "You are already in your selected market region."
}
```



## Home

### Home

Method: `GET`  
URL: `/api/v1/home/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "current_selection": {
    "mode": "service_city",
    "label": "الجزائر",
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": 250.0,
      "is_active": true
    },
    "updated_at": "2026-07-05T07:25:54.171625Z"
  },
  "location": {
    "address_id": 1,
    "name": "المنزل",
    "latitude": 36.7525,
    "longitude": 3.0419
  },
  "offers": [
    {
      "id": 4,
      "title": "غداء الجزائر السريع",
      "description": "عرض تجريبي: غداء الجزائر السريع.",
      "image": null,
      "type": "flash",
      "discount": "12.00",
      "start_time": "2026-07-04T07:25:39.440065Z",
      "end_time": "2026-08-04T07:25:39.440065Z",
      "active_days": [
        0,
        "... 6 more item(s)"
      ],
      "use_limits": 500,
      "user_limit": 3,
      "status": "active",
      "market": {
        "id": 2,
        "name": "مطبخ أطلس العائلي",
        "branch": "باب الزوار",
        "scope": "service_city",
        "status": "active",
        "classification_id": 2,
        "service_cities": [
          {
            "id": 1,
            "name": "الجزائر",
            "delivery_price": "250.00",
            "is_active": true
          }
        ],
        "delivery_areas": [
          {
            "id": 1,
            "service_city_id": 1,
            "name": "وسط الجزائر",
            "delivery_price": "250.00",
            "center_latitude": "36.7538000",
            "center_longitude": "3.0588000",
            "radius_km": "8.00",
            "is_active": true
          },
          "... 1 more item(s)"
        ]
      },
      "products": [
        {
          "id": 7,
          "name": "شوربة خضار",
          "description": "منتج تجريبي: شوربة خضار.",
          "image": null,
          "discount": "0.00",
          "category": {
            "id": 4,
            "name": "وجبات",
            "type": "meal",
            "description": "وجبات جاهزة للأكل",
            "image": null,
            "classification_id": 2
          },
          "market": {
            "id": 2,
            "name": "مطبخ أطلس العائلي",
            "branch": "باب الزوار",
            "scope": "service_city",
            "status": "active",
            "classification_id": 2,
            "service_cities": [
              {
                "id": 1,
                "name": "الجزائر",
                "delivery_price": "250.00",
                "is_active": true
              }
            ],
            "delivery_areas": [
              {
                "id": 1,
                "service_city_id": 1,
                "name": "وسط الجزائر",
                "delivery_price": "250.00",
                "center_latitude": "36.7538000",
                "center_longitude": "3.0588000",
                "radius_km": "8.00",
                "is_active": true
              },
              "... 1 more item(s)"
            ]
          },
          "variants": [
            {
              "id": 13,
              "price": "420.00",
              "sku": "SEED-07-1"
            },
            "... 1 more item(s)"
          ]
        },
        "... 1 more item(s)"
      ]
    },
    "... 1 more item(s)"
  ],
  "market_classifications": [
    {
      "id": 2,
      "name": "مطعم",
      "classification_type": "featured",
      "markets": [
        {
          "id": 2,
          "name": "مطبخ أطلس العائلي",
          "branch": "باب الزوار",
          "scope": "service_city",
          "status": "active",
          "classification_id": 2,
          "service_cities": [
            {
              "id": 1,
              "name": "الجزائر",
              "delivery_price": "250.00",
              "is_active": true
            }
          ],
          "delivery_areas": [
            {
              "id": 1,
              "service_city_id": 1,
              "name": "وسط الجزائر",
              "delivery_price": "250.00",
              "center_latitude": "36.7538000",
              "center_longitude": "3.0588000",
              "radius_km": "8.00",
              "is_active": true
            },
            "... 1 more item(s)"
          ]
        }
      ]
    }
  ],
  "products": [
    {
      "id": 8,
      "name": "دجاج مشوي",
      "description": "منتج تجريبي: دجاج مشوي.",
      "image": null,
      "discount": "0.00",
      "category": {
        "id": 4,
        "name": "وجبات",
        "type": "meal",
        "description": "وجبات جاهزة للأكل",
        "image": null,
        "classification_id": 2
      },
      "market": {
        "id": 2,
        "name": "مطبخ أطلس العائلي",
        "branch": "باب الزوار",
        "scope": "service_city",
        "status": "active",
        "classification_id": 2,
        "service_cities": [
          {
            "id": 1,
            "name": "الجزائر",
            "delivery_price": "250.00",
            "is_active": true
          }
        ],
        "delivery_areas": [
          {
            "id": 1,
            "service_city_id": 1,
            "name": "وسط الجزائر",
            "delivery_price": "250.00",
            "center_latitude": "36.7538000",
            "center_longitude": "3.0588000",
            "radius_km": "8.00",
            "is_active": true
          },
          "... 1 more item(s)"
        ]
      },
      "variants": [
        {
          "id": 15,
          "price": "980.00",
          "sku": "SEED-08-1"
        },
        "... 1 more item(s)"
      ]
    },
    "... 2 more item(s)"
  ]
}
```



### Home search

Method: `GET`  
URL: `/api/v1/home/search/?q=seed`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "count": 0,
  "next": null,
  "previous": null,
  "results": []
}
```



### Home products

Method: `GET`  
URL: `/api/v1/home/products/?order_by_latest=true`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "count": 3,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 8,
      "name": "دجاج مشوي",
      "description": "منتج تجريبي: دجاج مشوي.",
      "image": null,
      "discount": "0.00",
      "category": {
        "id": 4,
        "name": "وجبات",
        "type": "meal",
        "description": "وجبات جاهزة للأكل",
        "image": null,
        "classification_id": 2
      },
      "market": {
        "id": 2,
        "name": "مطبخ أطلس العائلي",
        "branch": "باب الزوار",
        "scope": "service_city",
        "status": "active",
        "classification_id": 2,
        "service_cities": [
          {
            "id": 1,
            "name": "الجزائر",
            "delivery_price": "250.00",
            "is_active": true
          }
        ],
        "delivery_areas": [
          {
            "id": 1,
            "service_city_id": 1,
            "name": "وسط الجزائر",
            "delivery_price": "250.00",
            "center_latitude": "36.7538000",
            "center_longitude": "3.0588000",
            "radius_km": "8.00",
            "is_active": true
          },
          "... 1 more item(s)"
        ]
      },
      "variants": [
        {
          "id": 15,
          "price": "980.00",
          "sku": "SEED-08-1"
        },
        "... 1 more item(s)"
      ]
    },
    "... 2 more item(s)"
  ]
}
```



### Home classifications

Method: `GET`  
URL: `/api/v1/home/classifications/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "common_market_classifications": [
    {
      "id": 2,
      "name": "مطعم",
      "classification_type": "featured",
      "product_count": 3
    }
  ],
  "market_classifications": [
    {
      "id": 2,
      "name": "مطعم",
      "classification_type": "featured",
      "product_count": 3,
      "markets": [
        {
          "id": 2,
          "name": "مطبخ أطلس العائلي",
          "branch": "باب الزوار",
          "status": "active",
          "classification_id": 2,
          "product_count": 3,
          "products": [
            {
              "id": 8,
              "name": "دجاج مشوي",
              "description": "منتج تجريبي: دجاج مشوي.",
              "image": null,
              "discount": "0.00",
              "category": {
                "id": 4,
                "name": "وجبات",
                "type": "meal",
                "description": "وجبات جاهزة للأكل",
                "image": null,
                "classification_id": 2
              }
            },
            "... 2 more item(s)"
          ]
        }
      ]
    }
  ]
}
```



### Featured classifications

Method: `GET`  
URL: `/api/v1/home/classifications/featured/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "current_selection": {
    "mode": "service_city",
    "label": "الجزائر",
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": 250.0,
      "is_active": true
    },
    "updated_at": "2026-07-05T07:25:54.171625Z"
  },
  "classifications": [
    {
      "id": 2,
      "name": "مطعم",
      "classification_type": "featured",
      "product_count": 3,
      "markets": [
        {
          "id": 2,
          "name": "مطبخ أطلس العائلي",
          "branch": "باب الزوار",
          "status": "active",
          "classification_id": 2,
          "product_count": 3,
          "products": [
            {
              "id": 8,
              "name": "دجاج مشوي",
              "description": "منتج تجريبي: دجاج مشوي.",
              "image": null,
              "discount": "0.00",
              "category": {
                "id": 4,
                "name": "وجبات",
                "type": "meal",
                "description": "وجبات جاهزة للأكل",
                "image": null,
                "classification_id": 2
              }
            },
            "... 2 more item(s)"
          ]
        }
      ]
    }
  ]
}
```



### Popular classifications

Method: `GET`  
URL: `/api/v1/home/classifications/popular/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "current_selection": {
    "mode": "service_city",
    "label": "الجزائر",
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": 250.0,
      "is_active": true
    },
    "updated_at": "2026-07-05T07:25:54.171625Z"
  },
  "classifications": []
}
```



### Normal classifications

Method: `GET`  
URL: `/api/v1/home/classifications/normal/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "current_selection": {
    "mode": "service_city",
    "label": "الجزائر",
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": 250.0,
      "is_active": true
    },
    "updated_at": "2026-07-05T07:25:54.171625Z"
  },
  "classifications": []
}
```



### Home product detail

Method: `GET`  
URL: `/api/v1/home/products/8/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": 8,
  "name": "دجاج مشوي",
  "description": "منتج تجريبي: دجاج مشوي.",
  "image": null,
  "discount": "0.00",
  "category": {
    "id": 4,
    "name": "وجبات",
    "type": "meal",
    "description": "وجبات جاهزة للأكل",
    "image": null,
    "classification_id": 2
  },
  "market": {
    "id": 2,
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "scope": "service_city",
    "status": "active",
    "classification_id": 2,
    "service_cities": [
      {
        "id": 1,
        "name": "الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      }
    ],
    "delivery_areas": [
      {
        "id": 1,
        "service_city_id": 1,
        "name": "وسط الجزائر",
        "delivery_price": "250.00",
        "center_latitude": "36.7538000",
        "center_longitude": "3.0588000",
        "radius_km": "8.00",
        "is_active": true
      },
      "... 1 more item(s)"
    ]
  },
  "variants": [
    {
      "id": 15,
      "price": "980.00",
      "sku": "SEED-08-1",
      "attribute_values": [
        {
          "id": 15,
          "attribute_id": 4,
          "attribute_name": "الحصة",
          "option_id": 7,
          "option_value": "عادية"
        }
      ]
    },
    "... 1 more item(s)"
  ],
  "attribute_values": [
    {
      "id": 8,
      "attribute_id": 4,
      "attribute_name": "الحصة",
      "option_id": 7,
      "option_value": "عادية"
    }
  ],
  "additions": [],
  "created_at": "2026-07-05T07:25:39.680871Z",
  "updated_at": "2026-07-05T07:25:39.680923Z"
}
```



### Classification markets

Method: `GET`  
URL: `/api/v1/home/classifications/4/markets/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "classification": {
    "id": 4,
    "name": "حلويات",
    "classification_type": "normal"
  },
  "markets": []
}
```



## Markets

### Admin market classification list

Method: `GET`  
URL: `/api/v1/home/market-classifications/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 4,
    "name": "حلويات",
    "classification_type": "normal"
  },
  "... 4 more item(s)"
]
```



### Admin market list

Method: `GET`  
URL: `/api/v1/home/markets/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 6,
    "classification": {
      "id": 4,
      "name": "حلويات",
      "classification_type": "normal"
    },
    "name": "حلويات الجسور",
    "branch": "الخروب",
    "scope": "service_city",
    "status": "active",
    "service_cities": [
      {
        "id": 3,
        "name": "قسنطينة",
        "delivery_price": "270.00",
        "is_active": true
      }
    ],
    "delivery_areas": [
      {
        "id": 5,
        "service_city_id": 3,
        "name": "وسط قسنطينة",
        "delivery_price": "270.00",
        "center_latitude": "36.3650000",
        "center_longitude": "6.6147000",
        "radius_km": "7.00",
        "is_active": true
      },
      "... 1 more item(s)"
    ],
    "created_at": "2026-07-05T07:25:39.567683Z",
    "updated_at": "2026-07-05T07:25:39.567723Z"
  },
  "... 7 more item(s)"
]
```



### Market classification create

Method: `POST`  
URL: `/api/v1/home/market-classifications/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "name": "Doc Market Class",
  "classification_type": "normal"
}
```

Response body:

```json
{
  "id": 6,
  "name": "Doc Market Class",
  "classification_type": "normal"
}
```



### Market classification detail

Method: `GET`  
URL: `/api/v1/home/market-classifications/6/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": 6,
  "name": "Doc Market Class",
  "classification_type": "normal"
}
```



### Market classification update

Method: `PATCH`  
URL: `/api/v1/home/market-classifications/6/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "classification_type": "featured"
}
```

Response body:

```json
{
  "id": 6,
  "name": "Doc Market Class",
  "classification_type": "featured"
}
```



### Market create

Method: `POST`  
URL: `/api/v1/home/markets/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "classification_id": 6,
  "name": "Doc Market",
  "branch": "Main",
  "scope": "service_city",
  "status": "active",
  "service_city_ids": [
    1
  ],
  "delivery_area_ids": [
    1
  ]
}
```

Response body:

```json
{
  "id": 9,
  "classification": {
    "id": 6,
    "name": "Doc Market Class",
    "classification_type": "featured"
  },
  "name": "Doc Market",
  "branch": "Main",
  "scope": "service_city",
  "status": "active",
  "service_cities": [
    {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    }
  ],
  "delivery_areas": [
    {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "center_latitude": "36.7538000",
      "center_longitude": "3.0588000",
      "radius_km": "8.00",
      "is_active": true
    }
  ],
  "created_at": "2026-07-05T07:25:55.354620Z",
  "updated_at": "2026-07-05T07:25:55.354670Z"
}
```



### Market detail

Method: `GET`  
URL: `/api/v1/home/markets/9/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": 9,
  "classification": {
    "id": 6,
    "name": "Doc Market Class",
    "classification_type": "featured"
  },
  "name": "Doc Market",
  "branch": "Main",
  "scope": "service_city",
  "status": "active",
  "service_cities": [
    {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    }
  ],
  "delivery_areas": [
    {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "center_latitude": "36.7538000",
      "center_longitude": "3.0588000",
      "radius_km": "8.00",
      "is_active": true
    }
  ],
  "created_at": "2026-07-05T07:25:55.354620Z",
  "updated_at": "2026-07-05T07:25:55.354670Z"
}
```



### Market update

Method: `PATCH`  
URL: `/api/v1/home/markets/9/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "branch": "Updated"
}
```

Response body:

```json
{
  "id": 9,
  "classification": {
    "id": 6,
    "name": "Doc Market Class",
    "classification_type": "featured"
  },
  "name": "Doc Market",
  "branch": "Updated",
  "scope": "service_city",
  "status": "active",
  "service_cities": [
    {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    }
  ],
  "delivery_areas": [
    {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "center_latitude": "36.7538000",
      "center_longitude": "3.0588000",
      "radius_km": "8.00",
      "is_active": true
    }
  ],
  "created_at": "2026-07-05T07:25:55.354620Z",
  "updated_at": "2026-07-05T07:25:55.439157Z"
}
```



### Market delete

Method: `DELETE`  
URL: `/api/v1/home/markets/9/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `204`


Request body:

```text
none
```

Response body:

```text
empty
```



### Market classification delete

Method: `DELETE`  
URL: `/api/v1/home/market-classifications/6/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `204`


Request body:

```text
none
```

Response body:

```text
empty
```



## Catalog

### Category classification list

Method: `GET`  
URL: `/api/v1/catalog/category-classifications/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 2,
    "name": "أكل جاهز"
  },
  "... 2 more item(s)"
]
```



### Product category list

Method: `GET`  
URL: `/api/v1/catalog/product-categories/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 5,
    "classification": {
      "id": 3,
      "name": "حلويات"
    },
    "name": "حلويات",
    "type": "dessert",
    "description": "حلويات تقليدية وعصرية",
    "image": null
  },
  "... 5 more item(s)"
]
```



### Addition classification list

Method: `GET`  
URL: `/api/v1/catalog/addition-classifications/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 3,
    "name": "إضافات"
  },
  "... 2 more item(s)"
]
```



### Category attribute list

Method: `GET`  
URL: `/api/v1/catalog/category-attributes/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 5,
    "category": {
      "id": 5,
      "classification": {
        "id": 3,
        "name": "حلويات"
      },
      "name": "حلويات",
      "type": "dessert",
      "description": "حلويات تقليدية وعصرية",
      "image": null
    },
    "name": "العبوة",
    "options": [
      {
        "id": 9,
        "value": "قطعتان"
      },
      "... 1 more item(s)"
    ]
  },
  "... 5 more item(s)"
]
```



### Category option list

Method: `GET`  
URL: `/api/v1/catalog/category-options/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 4,
    "attribute": {
      "id": 2,
      "name": "الحجم",
      "category_id": 2
    },
    "value": "1 لتر"
  },
  "... 11 more item(s)"
]
```



### Product addition list

Method: `GET`  
URL: `/api/v1/catalog/product-additions/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 3,
    "classification": {
      "id": 3,
      "name": "إضافات"
    },
    "products": [
      6,
      "... 1 more item(s)"
    ],
    "image": null,
    "name_ar": "خبز إضافي",
    "name_en": "خبز إضافي",
    "price": "40.00",
    "is_active": true
  },
  "... 5 more item(s)"
]
```



### Admin product list

Method: `GET`  
URL: `/api/v1/catalog/products/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 20,
    "market": {
      "id": 8,
      "name": "مخبزة المرجان",
      "branch": "البوني",
      "status": "active",
      "classification_id": 3
    },
    "category": {
      "id": 3,
      "classification": {
        "id": 2,
        "name": "أكل جاهز"
      },
      "name": "مخبوزات",
      "type": "bakery",
      "description": "خبز ومخبوزات يومية",
      "image": null,
      "attributes": [
        {
          "id": 3,
          "name": "العبوة",
          "options": [
            {
              "id": 5,
              "value": "قطعة واحدة"
            },
            "... 1 more item(s)"
          ]
        }
      ]
    },
    "is_available": true,
    "name": "بريوش",
    "description": "منتج تجريبي: بريوش.",
    "image": null,
    "discount": "0.00",
    "attribute_values": [
      {
        "id": 20,
        "attribute": {
          "id": 3,
          "name": "العبوة",
          "options": [
            {
              "id": 5,
              "value": "قطعة واحدة"
            },
            "... 1 more item(s)"
          ]
        },
        "option": {
          "id": 5,
          "value": "قطعة واحدة"
        }
      }
    ],
    "variants": [
      {
        "id": 39,
        "price": "160.00",
        "sku": "SEED-20-1",
        "attribute_values": [
          {
            "id": 39,
            "attribute": {
              "id": 3,
              "name": "العبوة",
              "options": [
                {
                  "id": 5,
                  "value": "قطعة واحدة"
                },
                "... 1 more item(s)"
              ]
            },
            "option": {
              "id": 5,
              "value": "قطعة واحدة"
            }
          }
        ]
      },
      "... 1 more item(s)"
    ],
    "additions": [
      6
    ],
    "created_at": "2026-07-05T07:25:39.784888Z",
    "updated_at": "2026-07-05T07:25:39.784931Z"
  },
  "... 19 more item(s)"
]
```



### Addition classification create

Method: `POST`  
URL: `/api/v1/catalog/addition-classifications/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "name": "Doc Addition Class"
}
```

Response body:

```json
{
  "id": 4,
  "name": "Doc Addition Class"
}
```



### Addition classification detail

Method: `GET`  
URL: `/api/v1/catalog/addition-classifications/4/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": 4,
  "name": "Doc Addition Class"
}
```



### Addition classification update

Method: `PATCH`  
URL: `/api/v1/catalog/addition-classifications/4/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "name": "Doc Addition Updated"
}
```

Response body:

```json
{
  "id": 4,
  "name": "Doc Addition Updated"
}
```



### Category classification create

Method: `POST`  
URL: `/api/v1/catalog/category-classifications/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "name": "Doc Category Class"
}
```

Response body:

```json
{
  "id": 4,
  "name": "Doc Category Class"
}
```



### Product category create

Method: `POST`  
URL: `/api/v1/catalog/product-categories/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "classification_id": 4,
  "name": "Doc Category",
  "type": "doc",
  "description": "Doc category"
}
```

Response body:

```json
{
  "id": 7,
  "classification": {
    "id": 4,
    "name": "Doc Category Class"
  },
  "name": "Doc Category",
  "type": "doc",
  "description": "Doc category",
  "image": null
}
```



### Category attribute create

Method: `POST`  
URL: `/api/v1/catalog/category-attributes/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "category_id": 7,
  "name": "Size"
}
```

Response body:

```json
{
  "id": 7,
  "category": {
    "id": 7,
    "classification": {
      "id": 4,
      "name": "Doc Category Class"
    },
    "name": "Doc Category",
    "type": "doc",
    "description": "Doc category",
    "image": null
  },
  "name": "Size",
  "options": []
}
```



### Category option create

Method: `POST`  
URL: `/api/v1/catalog/category-options/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "attribute_id": 7,
  "value": "Small"
}
```

Response body:

```json
{
  "id": 13,
  "attribute": {
    "id": 7,
    "name": "Size",
    "category_id": 7
  },
  "value": "Small"
}
```



### Product addition create

Method: `POST`  
URL: `/api/v1/catalog/product-additions/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "classification_id": 4,
  "name_ar": "إضافة",
  "name_en": "Doc Extra",
  "price": "3.50",
  "is_active": true
}
```

Response body:

```json
{
  "id": 7,
  "classification": {
    "id": 4,
    "name": "Doc Addition Updated"
  },
  "products": [],
  "image": null,
  "name_ar": "إضافة",
  "name_en": "Doc Extra",
  "price": "3.50",
  "is_active": true
}
```



### Product create

Method: `POST`  
URL: `/api/v1/catalog/products/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "market_id": 2,
  "category_id": 7,
  "is_available": true,
  "name": "Doc Product",
  "description": "Doc product",
  "discount": "0.00",
  "attribute_values": [
    {
      "attribute_id": 7,
      "option_id": 13
    }
  ],
  "variants": [
    {
      "price": "12.00",
      "sku": "DOC-1",
      "attribute_values": [
        {
          "attribute_id": 7,
          "option_id": 13
        }
      ]
    }
  ],
  "additions": [
    7
  ]
}
```

Response body:

```json
{
  "id": 21,
  "market": {
    "id": 2,
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "status": "active",
    "classification_id": 2
  },
  "category": {
    "id": 7,
    "classification": {
      "id": 4,
      "name": "Doc Category Class"
    },
    "name": "Doc Category",
    "type": "doc",
    "description": "Doc category",
    "image": null,
    "attributes": [
      {
        "id": 7,
        "name": "Size",
        "options": [
          {
            "id": 13,
            "value": "Small"
          }
        ]
      }
    ]
  },
  "is_available": true,
  "name": "Doc Product",
  "description": "Doc product",
  "image": null,
  "discount": "0.00",
  "attribute_values": [
    {
      "id": 21,
      "attribute": {
        "id": 7,
        "name": "Size",
        "options": [
          {
            "id": 13,
            "value": "Small"
          }
        ]
      },
      "option": {
        "id": 13,
        "value": "Small"
      }
    }
  ],
  "variants": [
    {
      "id": 41,
      "price": "12.00",
      "sku": "DOC-1",
      "attribute_values": [
        {
          "id": 41,
          "attribute": {
            "id": 7,
            "name": "Size",
            "options": [
              {
                "id": 13,
                "value": "Small"
              }
            ]
          },
          "option": {
            "id": 13,
            "value": "Small"
          }
        }
      ]
    }
  ],
  "additions": [
    7
  ],
  "created_at": "2026-07-05T07:25:55.778065Z",
  "updated_at": "2026-07-05T07:25:55.778102Z"
}
```



### Product category detail

Method: `GET`  
URL: `/api/v1/catalog/product-categories/7/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": 7,
  "classification": {
    "id": 4,
    "name": "Doc Category Class"
  },
  "name": "Doc Category",
  "type": "doc",
  "description": "Doc category",
  "image": null
}
```



### Category attribute detail

Method: `GET`  
URL: `/api/v1/catalog/category-attributes/7/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": 7,
  "category": {
    "id": 7,
    "classification": {
      "id": 4,
      "name": "Doc Category Class"
    },
    "name": "Doc Category",
    "type": "doc",
    "description": "Doc category",
    "image": null
  },
  "name": "Size",
  "options": [
    {
      "id": 13,
      "value": "Small"
    }
  ]
}
```



### Category option detail

Method: `GET`  
URL: `/api/v1/catalog/category-options/13/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": 13,
  "attribute": {
    "id": 7,
    "name": "Size",
    "category_id": 7
  },
  "value": "Small"
}
```



### Product addition detail

Method: `GET`  
URL: `/api/v1/catalog/product-additions/7/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": 7,
  "classification": {
    "id": 4,
    "name": "Doc Addition Updated"
  },
  "products": [
    21
  ],
  "image": null,
  "name_ar": "إضافة",
  "name_en": "Doc Extra",
  "price": "3.50",
  "is_active": true
}
```



### Product detail

Method: `GET`  
URL: `/api/v1/catalog/products/21/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": 21,
  "market": {
    "id": 2,
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "status": "active",
    "classification_id": 2
  },
  "category": {
    "id": 7,
    "classification": {
      "id": 4,
      "name": "Doc Category Class"
    },
    "name": "Doc Category",
    "type": "doc",
    "description": "Doc category",
    "image": null,
    "attributes": [
      {
        "id": 7,
        "name": "Size",
        "options": [
          {
            "id": 13,
            "value": "Small"
          }
        ]
      }
    ]
  },
  "is_available": true,
  "name": "Doc Product",
  "description": "Doc product",
  "image": null,
  "discount": "0.00",
  "attribute_values": [
    {
      "id": 21,
      "attribute": {
        "id": 7,
        "name": "Size",
        "options": [
          {
            "id": 13,
            "value": "Small"
          }
        ]
      },
      "option": {
        "id": 13,
        "value": "Small"
      }
    }
  ],
  "variants": [
    {
      "id": 41,
      "price": "12.00",
      "sku": "DOC-1",
      "attribute_values": [
        {
          "id": 41,
          "attribute": {
            "id": 7,
            "name": "Size",
            "options": [
              {
                "id": 13,
                "value": "Small"
              }
            ]
          },
          "option": {
            "id": 13,
            "value": "Small"
          }
        }
      ]
    }
  ],
  "additions": [
    7
  ],
  "created_at": "2026-07-05T07:25:55.778065Z",
  "updated_at": "2026-07-05T07:25:55.778102Z"
}
```



### Product update

Method: `PATCH`  
URL: `/api/v1/catalog/products/21/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "name": "Doc Product Updated"
}
```

Response body:

```json
{
  "id": 21,
  "market": {
    "id": 2,
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "status": "active",
    "classification_id": 2
  },
  "category": {
    "id": 7,
    "classification": {
      "id": 4,
      "name": "Doc Category Class"
    },
    "name": "Doc Category",
    "type": "doc",
    "description": "Doc category",
    "image": null,
    "attributes": [
      {
        "id": 7,
        "name": "Size",
        "options": [
          {
            "id": 13,
            "value": "Small"
          }
        ]
      }
    ]
  },
  "is_available": true,
  "name": "Doc Product Updated",
  "description": "Doc product",
  "image": null,
  "discount": "0.00",
  "attribute_values": [
    {
      "id": 21,
      "attribute": {
        "id": 7,
        "name": "Size",
        "options": [
          {
            "id": 13,
            "value": "Small"
          }
        ]
      },
      "option": {
        "id": 13,
        "value": "Small"
      }
    }
  ],
  "variants": [
    {
      "id": 41,
      "price": "12.00",
      "sku": "DOC-1",
      "attribute_values": [
        {
          "id": 41,
          "attribute": {
            "id": 7,
            "name": "Size",
            "options": [
              {
                "id": 13,
                "value": "Small"
              }
            ]
          },
          "option": {
            "id": 13,
            "value": "Small"
          }
        }
      ]
    }
  ],
  "additions": [
    7
  ],
  "created_at": "2026-07-05T07:25:55.778065Z",
  "updated_at": "2026-07-05T07:25:56.006181Z"
}
```



### Liked products

Method: `GET`  
URL: `/api/v1/catalog/products/likes/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[]
```



### Like product

Method: `POST`  
URL: `/api/v1/catalog/products/8/like/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "product_id": 8,
  "liked": true
}
```



### Unlike product

Method: `DELETE`  
URL: `/api/v1/catalog/products/8/unlike/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "product_id": 8,
  "liked": false
}
```



### Product delete

Method: `DELETE`  
URL: `/api/v1/catalog/products/21/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `204`


Request body:

```text
none
```

Response body:

```text
empty
```



### Product addition delete

Method: `DELETE`  
URL: `/api/v1/catalog/product-additions/7/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `204`


Request body:

```text
none
```

Response body:

```text
empty
```



### Category option delete

Method: `DELETE`  
URL: `/api/v1/catalog/category-options/13/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "details": "Deleted Successfully"
}
```



### Category attribute delete

Method: `DELETE`  
URL: `/api/v1/catalog/category-attributes/7/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "details": "Deleted Successfully"
}
```



### Product category delete

Method: `DELETE`  
URL: `/api/v1/catalog/product-categories/7/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "details": "Deleted Successfully"
}
```



### Category classification delete

Method: `DELETE`  
URL: `/api/v1/catalog/category-classifications/4/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "details": "Deleted Successfully"
}
```



### Addition classification delete

Method: `DELETE`  
URL: `/api/v1/catalog/addition-classifications/4/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "details": "Deleted Successfully"
}
```



## Offers

### Admin offer list

Method: `GET`  
URL: `/api/v1/offers/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 9,
    "market": {
      "id": 8,
      "classification": {
        "id": 3,
        "name": "مخبزة",
        "classification_type": "normal"
      },
      "name": "مخبزة المرجان",
      "branch": "البوني",
      "scope": "service_city",
      "status": "active",
      "service_cities": [
        {
          "id": 4,
          "name": "عنابة",
          "delivery_price": "260.00",
          "is_active": true
        }
      ],
      "delivery_areas": [
        {
          "id": 7,
          "service_city_id": 4,
          "name": "وسط عنابة",
          "delivery_price": "260.00",
          "center_latitude": "36.9000000",
          "center_longitude": "7.7667000",
          "radius_km": "7.00",
          "is_active": true
        },
        "... 1 more item(s)"
      ],
      "created_at": "2026-07-05T07:25:39.576025Z",
      "updated_at": "2026-07-05T07:25:39.576057Z"
    },
    "market_id": 8,
    "scope": "service_city",
    "service_city": {
      "id": 4,
      "name": "عنابة",
      "delivery_price": "260.00",
      "is_active": true
    },
    "service_city_id": 4,
    "products": [
      {
        "id": 19,
        "market_id": 8,
        "category_id": 3,
        "is_available": true,
        "name": "خبز كامل",
        "description": "منتج تجريبي: خبز كامل.",
        "image": null,
        "discount": "0.00",
        "created_at": "2026-07-05T07:25:39.775677Z",
        "updated_at": "2026-07-05T07:25:39.775710Z"
      },
      "... 1 more item(s)"
    ],
    "product_ids": [
      19,
      "... 1 more item(s)"
    ],
    "title": "توصيل مخبزة المرجان",
    "description": "عرض تجريبي: توصيل مخبزة المرجان.",
    "image": null,
    "type": "delivery",
    "discount": "7.00",
    "start_time": "2026-07-04T07:25:39.440065Z",
    "end_time": "2026-08-04T07:25:39.440065Z",
    "active_days": [
      0,
      "... 6 more item(s)"
    ],
    "use_limits": 500,
    "user_limit": 3,
    "status": "active",
    "created_at": "2026-07-05T07:25:39.857820Z",
    "updated_at": "2026-07-05T07:25:39.857841Z"
  },
  "... 8 more item(s)"
]
```



### Offer create JSON

Method: `POST`  
URL: `/api/v1/offers/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "market_id": 2,
  "scope": "service_city",
  "service_city_id": 1,
  "product_ids": [
    8
  ],
  "title": "Doc JSON Offer",
  "description": "Doc offer",
  "type": "flash",
  "discount": "5.00",
  "start_time": "2026-07-05T06:00:00Z",
  "end_time": "2026-07-10T06:00:00Z",
  "active_days": [
    "sunday"
  ],
  "use_limits": 10,
  "user_limit": 1,
  "status": "active"
}
```

Response body:

```json
{
  "id": 10,
  "market": {
    "id": 2,
    "classification": {
      "id": 2,
      "name": "مطعم",
      "classification_type": "featured"
    },
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "scope": "service_city",
    "status": "active",
    "service_cities": [
      {
        "id": 1,
        "name": "الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      }
    ],
    "delivery_areas": [
      {
        "id": 1,
        "service_city_id": 1,
        "name": "وسط الجزائر",
        "delivery_price": "250.00",
        "center_latitude": "36.7538000",
        "center_longitude": "3.0588000",
        "radius_km": "8.00",
        "is_active": true
      },
      "... 1 more item(s)"
    ],
    "created_at": "2026-07-05T07:25:39.549810Z",
    "updated_at": "2026-07-05T07:25:39.549855Z"
  },
  "market_id": 2,
  "scope": "service_city",
  "service_city": {
    "id": 1,
    "name": "الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "service_city_id": 1,
  "products": [
    {
      "id": 8,
      "market_id": 2,
      "category_id": 4,
      "is_available": true,
      "name": "دجاج مشوي",
      "description": "منتج تجريبي: دجاج مشوي.",
      "image": null,
      "discount": "0.00",
      "created_at": "2026-07-05T07:25:39.680871Z",
      "updated_at": "2026-07-05T07:25:39.680923Z"
    }
  ],
  "product_ids": [
    8
  ],
  "title": "Doc JSON Offer",
  "description": "Doc offer",
  "image": null,
  "type": "flash",
  "discount": "5.00",
  "start_time": "2026-07-05T06:00:00Z",
  "end_time": "2026-07-10T06:00:00Z",
  "active_days": [
    "sunday"
  ],
  "use_limits": 10,
  "user_limit": 1,
  "status": "active",
  "created_at": "2026-07-05T07:25:56.400182Z",
  "updated_at": "2026-07-05T07:25:56.400210Z"
}
```



### Offer create multipart image

Method: `POST`  
URL: `/api/v1/offers/`  
Auth: Admin token  
Content-Type: `multipart/form-data`  
HTTP status: `201`


Request body:

```json
{
  "market_id": 2,
  "scope": "service_city",
  "service_city_id": 1,
  "product_ids": [
    8
  ],
  "title": "Doc Multipart Offer",
  "description": "Doc offer",
  "type": "flash",
  "discount": "5.00",
  "start_time": "2026-07-05T06:00:00Z",
  "end_time": "2026-07-10T06:00:00Z",
  "active_days": "[\"sunday\"]",
  "use_limits": 10,
  "user_limit": 1,
  "status": "active",
  "image": "<file offer.gif>"
}
```

Response body:

```json
{
  "id": 11,
  "market": {
    "id": 2,
    "classification": {
      "id": 2,
      "name": "مطعم",
      "classification_type": "featured"
    },
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "scope": "service_city",
    "status": "active",
    "service_cities": [
      {
        "id": 1,
        "name": "الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      }
    ],
    "delivery_areas": [
      {
        "id": 1,
        "service_city_id": 1,
        "name": "وسط الجزائر",
        "delivery_price": "250.00",
        "center_latitude": "36.7538000",
        "center_longitude": "3.0588000",
        "radius_km": "8.00",
        "is_active": true
      },
      "... 1 more item(s)"
    ],
    "created_at": "2026-07-05T07:25:39.549810Z",
    "updated_at": "2026-07-05T07:25:39.549855Z"
  },
  "market_id": 2,
  "scope": "service_city",
  "service_city": {
    "id": 1,
    "name": "الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "service_city_id": 1,
  "products": [
    {
      "id": 8,
      "market_id": 2,
      "category_id": 4,
      "is_available": true,
      "name": "دجاج مشوي",
      "description": "منتج تجريبي: دجاج مشوي.",
      "image": null,
      "discount": "0.00",
      "created_at": "2026-07-05T07:25:39.680871Z",
      "updated_at": "2026-07-05T07:25:39.680923Z"
    }
  ],
  "product_ids": [
    8
  ],
  "title": "Doc Multipart Offer",
  "description": "Doc offer",
  "image": "/media/offers/offer.gif",
  "type": "flash",
  "discount": "5.00",
  "start_time": "2026-07-05T06:00:00Z",
  "end_time": "2026-07-10T06:00:00Z",
  "active_days": [
    "sunday"
  ],
  "use_limits": 10,
  "user_limit": 1,
  "status": "active",
  "created_at": "2026-07-05T07:25:56.589832Z",
  "updated_at": "2026-07-05T07:25:56.589860Z"
}
```



### Offer detail

Method: `GET`  
URL: `/api/v1/offers/10/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": 10,
  "market": {
    "id": 2,
    "classification": {
      "id": 2,
      "name": "مطعم",
      "classification_type": "featured"
    },
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "scope": "service_city",
    "status": "active",
    "service_cities": [
      {
        "id": 1,
        "name": "الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      }
    ],
    "delivery_areas": [
      {
        "id": 1,
        "service_city_id": 1,
        "name": "وسط الجزائر",
        "delivery_price": "250.00",
        "center_latitude": "36.7538000",
        "center_longitude": "3.0588000",
        "radius_km": "8.00",
        "is_active": true
      },
      "... 1 more item(s)"
    ],
    "created_at": "2026-07-05T07:25:39.549810Z",
    "updated_at": "2026-07-05T07:25:39.549855Z"
  },
  "market_id": 2,
  "scope": "service_city",
  "service_city": {
    "id": 1,
    "name": "الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "service_city_id": 1,
  "products": [
    {
      "id": 8,
      "market_id": 2,
      "category_id": 4,
      "is_available": true,
      "name": "دجاج مشوي",
      "description": "منتج تجريبي: دجاج مشوي.",
      "image": null,
      "discount": "0.00",
      "created_at": "2026-07-05T07:25:39.680871Z",
      "updated_at": "2026-07-05T07:25:39.680923Z"
    }
  ],
  "product_ids": [
    8
  ],
  "title": "Doc JSON Offer",
  "description": "Doc offer",
  "image": null,
  "type": "flash",
  "discount": "5.00",
  "start_time": "2026-07-05T06:00:00Z",
  "end_time": "2026-07-10T06:00:00Z",
  "active_days": [
    "sunday"
  ],
  "use_limits": 10,
  "user_limit": 1,
  "status": "active",
  "created_at": "2026-07-05T07:25:56.400182Z",
  "updated_at": "2026-07-05T07:25:56.400210Z"
}
```



### Offer update

Method: `PATCH`  
URL: `/api/v1/offers/10/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "title": "Doc Offer Updated"
}
```

Response body:

```json
{
  "id": 10,
  "market": {
    "id": 2,
    "classification": {
      "id": 2,
      "name": "مطعم",
      "classification_type": "featured"
    },
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "scope": "service_city",
    "status": "active",
    "service_cities": [
      {
        "id": 1,
        "name": "الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      }
    ],
    "delivery_areas": [
      {
        "id": 1,
        "service_city_id": 1,
        "name": "وسط الجزائر",
        "delivery_price": "250.00",
        "center_latitude": "36.7538000",
        "center_longitude": "3.0588000",
        "radius_km": "8.00",
        "is_active": true
      },
      "... 1 more item(s)"
    ],
    "created_at": "2026-07-05T07:25:39.549810Z",
    "updated_at": "2026-07-05T07:25:39.549855Z"
  },
  "market_id": 2,
  "scope": "service_city",
  "service_city": {
    "id": 1,
    "name": "الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "service_city_id": 1,
  "products": [
    {
      "id": 8,
      "market_id": 2,
      "category_id": 4,
      "is_available": true,
      "name": "دجاج مشوي",
      "description": "منتج تجريبي: دجاج مشوي.",
      "image": null,
      "discount": "0.00",
      "created_at": "2026-07-05T07:25:39.680871Z",
      "updated_at": "2026-07-05T07:25:39.680923Z"
    }
  ],
  "product_ids": [
    8
  ],
  "title": "Doc Offer Updated",
  "description": "Doc offer",
  "image": null,
  "type": "flash",
  "discount": "5.00",
  "start_time": "2026-07-05T06:00:00Z",
  "end_time": "2026-07-10T06:00:00Z",
  "active_days": [
    "sunday"
  ],
  "use_limits": 10,
  "user_limit": 1,
  "status": "active",
  "created_at": "2026-07-05T07:25:56.400182Z",
  "updated_at": "2026-07-05T07:25:56.703928Z"
}
```



### Client offer list

Method: `GET`  
URL: `/api/v1/offers/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 11,
    "title": "Doc Multipart Offer",
    "description": "Doc offer",
    "image": "http://127.0.0.1:8765/media/offers/offer.gif",
    "type": "flash",
    "discount": "5.00",
    "start_time": "2026-07-05T06:00:00Z",
    "end_time": "2026-07-10T06:00:00Z",
    "active_days": [
      "sunday"
    ],
    "use_limits": 10,
    "user_limit": 1,
    "status": "active",
    "market": {
      "id": 2,
      "name": "مطبخ أطلس العائلي",
      "branch": "باب الزوار",
      "scope": "service_city",
      "status": "active",
      "classification_id": 2,
      "service_cities": [
        {
          "id": 1,
          "name": "الجزائر",
          "delivery_price": "250.00",
          "is_active": true
        }
      ],
      "delivery_areas": [
        {
          "id": 1,
          "service_city_id": 1,
          "name": "وسط الجزائر",
          "delivery_price": "250.00",
          "center_latitude": "36.7538000",
          "center_longitude": "3.0588000",
          "radius_km": "8.00",
          "is_active": true
        },
        "... 1 more item(s)"
      ]
    },
    "products": [
      {
        "id": 8,
        "name": "دجاج مشوي",
        "description": "منتج تجريبي: دجاج مشوي.",
        "image": null,
        "discount": "0.00",
        "category": {
          "id": 4,
          "name": "وجبات",
          "type": "meal",
          "description": "وجبات جاهزة للأكل",
          "image": null,
          "classification_id": 2
        },
        "market": {
          "id": 2,
          "name": "مطبخ أطلس العائلي",
          "branch": "باب الزوار",
          "scope": "service_city",
          "status": "active",
          "classification_id": 2,
          "service_cities": [
            {
              "id": 1,
              "name": "الجزائر",
              "delivery_price": "250.00",
              "is_active": true
            }
          ],
          "delivery_areas": [
            {
              "id": 1,
              "service_city_id": 1,
              "name": "وسط الجزائر",
              "delivery_price": "250.00",
              "center_latitude": "36.7538000",
              "center_longitude": "3.0588000",
              "radius_km": "8.00",
              "is_active": true
            },
            "... 1 more item(s)"
          ]
        },
        "variants": [
          {
            "id": 15,
            "price": "980.00",
            "sku": "SEED-08-1"
          },
          "... 1 more item(s)"
        ]
      }
    ]
  },
  "... 3 more item(s)"
]
```



### Client offer detail

Method: `GET`  
URL: `/api/v1/offers/10/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": 10,
  "title": "Doc Offer Updated",
  "description": "Doc offer",
  "image": null,
  "type": "flash",
  "discount": "5.00",
  "start_time": "2026-07-05T06:00:00Z",
  "end_time": "2026-07-10T06:00:00Z",
  "active_days": [
    "sunday"
  ],
  "use_limits": 10,
  "user_limit": 1,
  "status": "active",
  "market": {
    "id": 2,
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "scope": "service_city",
    "status": "active",
    "classification_id": 2,
    "service_cities": [
      {
        "id": 1,
        "name": "الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      }
    ],
    "delivery_areas": [
      {
        "id": 1,
        "service_city_id": 1,
        "name": "وسط الجزائر",
        "delivery_price": "250.00",
        "center_latitude": "36.7538000",
        "center_longitude": "3.0588000",
        "radius_km": "8.00",
        "is_active": true
      },
      "... 1 more item(s)"
    ]
  },
  "products": [
    {
      "id": 8,
      "name": "دجاج مشوي",
      "description": "منتج تجريبي: دجاج مشوي.",
      "image": null,
      "discount": "0.00",
      "category": {
        "id": 4,
        "name": "وجبات",
        "type": "meal",
        "description": "وجبات جاهزة للأكل",
        "image": null,
        "classification_id": 2
      },
      "market": {
        "id": 2,
        "name": "مطبخ أطلس العائلي",
        "branch": "باب الزوار",
        "scope": "service_city",
        "status": "active",
        "classification_id": 2,
        "service_cities": [
          {
            "id": 1,
            "name": "الجزائر",
            "delivery_price": "250.00",
            "is_active": true
          }
        ],
        "delivery_areas": [
          {
            "id": 1,
            "service_city_id": 1,
            "name": "وسط الجزائر",
            "delivery_price": "250.00",
            "center_latitude": "36.7538000",
            "center_longitude": "3.0588000",
            "radius_km": "8.00",
            "is_active": true
          },
          "... 1 more item(s)"
        ]
      },
      "variants": [
        {
          "id": 15,
          "price": "980.00",
          "sku": "SEED-08-1"
        },
        "... 1 more item(s)"
      ]
    }
  ]
}
```



### Offer delete

Method: `DELETE`  
URL: `/api/v1/offers/11/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "details": "Deleted Successfully"
}
```



## Locations

### Service city list

Method: `GET`  
URL: `/api/v1/locations/service-cities/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 1,
    "name": "الجزائر",
    "center_latitude": "36.7538000",
    "center_longitude": "3.0588000",
    "radius_km": "35.00",
    "delivery_price": "250.00",
    "is_active": true
  },
  "... 3 more item(s)"
]
```



### Delivery area list

Method: `GET`  
URL: `/api/v1/locations/delivery-areas/?service_city_id=1`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 2,
    "service_city_id": 1,
    "name": "باب الزوار",
    "center_latitude": "36.7167000",
    "center_longitude": "3.1833000",
    "radius_km": "6.50",
    "delivery_price": "300.00",
    "is_active": true
  },
  "... 1 more item(s)"
]
```



### Service city create

Method: `POST`  
URL: `/api/v1/locations/service-cities/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "name": "Doc City",
  "center_latitude": "31.1000000",
  "center_longitude": "3.1000000",
  "radius_km": "10.00",
  "delivery_price": "15.00",
  "is_active": true
}
```

Response body:

```json
{
  "id": 5,
  "name": "Doc City",
  "center_latitude": "31.1000000",
  "center_longitude": "3.1000000",
  "radius_km": "10.00",
  "delivery_price": "15.00",
  "is_active": true
}
```



### Service city detail

Method: `GET`  
URL: `/api/v1/locations/service-cities/5/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": 5,
  "name": "Doc City",
  "center_latitude": "31.1000000",
  "center_longitude": "3.1000000",
  "radius_km": "10.00",
  "delivery_price": "15.00",
  "is_active": true
}
```



### Service city update

Method: `PATCH`  
URL: `/api/v1/locations/service-cities/5/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "delivery_price": "16.00"
}
```

Response body:

```json
{
  "id": 5,
  "name": "Doc City",
  "center_latitude": "31.1000000",
  "center_longitude": "3.1000000",
  "radius_km": "10.00",
  "delivery_price": "16.00",
  "is_active": true
}
```



### Service city replace

Method: `PUT`  
URL: `/api/v1/locations/service-cities/5/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "name": "Doc City",
  "center_latitude": "31.1000000",
  "center_longitude": "3.1000000",
  "radius_km": "10.00",
  "delivery_price": "16.00",
  "is_active": true
}
```

Response body:

```json
{
  "id": 5,
  "name": "Doc City",
  "center_latitude": "31.1000000",
  "center_longitude": "3.1000000",
  "radius_km": "10.00",
  "delivery_price": "16.00",
  "is_active": true
}
```



### Delivery area create

Method: `POST`  
URL: `/api/v1/locations/delivery-areas/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "service_city_id": 5,
  "name": "Doc Area",
  "center_latitude": "31.1000000",
  "center_longitude": "3.1000000",
  "radius_km": "5.00",
  "delivery_price": "4.00",
  "is_active": true
}
```

Response body:

```json
{
  "id": 9,
  "service_city_id": 5,
  "name": "Doc Area",
  "center_latitude": "31.1000000",
  "center_longitude": "3.1000000",
  "radius_km": "5.00",
  "delivery_price": "4.00",
  "is_active": true
}
```



### Delivery area detail

Method: `GET`  
URL: `/api/v1/locations/delivery-areas/9/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": 9,
  "service_city_id": 5,
  "name": "Doc Area",
  "center_latitude": "31.1000000",
  "center_longitude": "3.1000000",
  "radius_km": "5.00",
  "delivery_price": "4.00",
  "is_active": true
}
```



### Delivery area update

Method: `PATCH`  
URL: `/api/v1/locations/delivery-areas/9/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "delivery_price": "5.00"
}
```

Response body:

```json
{
  "id": 9,
  "service_city_id": 5,
  "name": "Doc Area",
  "center_latitude": "31.1000000",
  "center_longitude": "3.1000000",
  "radius_km": "5.00",
  "delivery_price": "5.00",
  "is_active": true
}
```



### Delivery area replace

Method: `PUT`  
URL: `/api/v1/locations/delivery-areas/9/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "service_city_id": 5,
  "name": "Doc Area",
  "center_latitude": "31.1000000",
  "center_longitude": "3.1000000",
  "radius_km": "5.00",
  "delivery_price": "5.00",
  "is_active": true
}
```

Response body:

```json
{
  "id": 9,
  "service_city_id": 5,
  "name": "Doc Area",
  "center_latitude": "31.1000000",
  "center_longitude": "3.1000000",
  "radius_km": "5.00",
  "delivery_price": "5.00",
  "is_active": true
}
```



### Delivery area delete

Method: `DELETE`  
URL: `/api/v1/locations/delivery-areas/9/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `204`


Request body:

```text
none
```

Response body:

```text
empty
```



### Service city delete

Method: `DELETE`  
URL: `/api/v1/locations/service-cities/5/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `204`


Request body:

```text
none
```

Response body:

```text
empty
```



## Addresses

### Address list

Method: `GET`  
URL: `/api/v1/addresses/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 1,
    "name": "المنزل",
    "fullName": "المنزل",
    "phone": "+213555100002",
    "phoneNumber": "+213555100002",
    "line1": "المنزل",
    "street": "المنزل",
    "city": "الجزائر",
    "state": "",
    "country": "Egypt",
    "postalCode": "",
    "latitude": "36.7525000",
    "longitude": "3.0419000",
    "details": "",
    "manual_city": null,
    "manual_area": null,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "center_latitude": "36.7538000",
      "center_longitude": "3.0588000",
      "radius_km": "35.00",
      "delivery_price": "250.00",
      "is_active": true
    },
    "service_city_id": 1,
    "service_city_name": "الجزائر",
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area_id": 1,
    "delivery_area_name": "وسط الجزائر",
    "delivery_area_price": "250.00",
    "delivery_type": "fixed_area",
    "delivery_price_preview": "250.00",
    "is_default": true,
    "isDefault": true,
    "created_at": "2026-07-05T07:25:39.513913Z"
  },
  "... 1 more item(s)"
]
```



### Address create

Method: `POST`  
URL: `/api/v1/addresses/`  
Auth: Client token  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "name": "Doc Address",
  "line1": "Doc Street",
  "service_city_id": 1,
  "delivery_area_id": 1,
  "delivery_type": "fixed_area",
  "is_default": false
}
```

Response body:

```json
[
  {
    "id": 1,
    "name": "المنزل",
    "fullName": "المنزل",
    "phone": "+213555100002",
    "phoneNumber": "+213555100002",
    "line1": "المنزل",
    "street": "المنزل",
    "city": "الجزائر",
    "state": "",
    "country": "Egypt",
    "postalCode": "",
    "latitude": "36.7525000",
    "longitude": "3.0419000",
    "details": "",
    "manual_city": null,
    "manual_area": null,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "center_latitude": "36.7538000",
      "center_longitude": "3.0588000",
      "radius_km": "35.00",
      "delivery_price": "250.00",
      "is_active": true
    },
    "service_city_id": 1,
    "service_city_name": "الجزائر",
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area_id": 1,
    "delivery_area_name": "وسط الجزائر",
    "delivery_area_price": "250.00",
    "delivery_type": "fixed_area",
    "delivery_price_preview": "250.00",
    "is_default": true,
    "isDefault": true,
    "created_at": "2026-07-05T07:25:39.513913Z"
  },
  "... 2 more item(s)"
]
```



### Default address

Method: `GET`  
URL: `/api/v1/addresses/default/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": 1,
  "name": "المنزل",
  "fullName": "المنزل",
  "phone": "+213555100002",
  "phoneNumber": "+213555100002",
  "line1": "المنزل",
  "street": "المنزل",
  "city": "الجزائر",
  "state": "",
  "country": "Egypt",
  "postalCode": "",
  "latitude": "36.7525000",
  "longitude": "3.0419000",
  "details": "",
  "manual_city": null,
  "manual_area": null,
  "service_city": {
    "id": 1,
    "name": "الجزائر",
    "center_latitude": "36.7538000",
    "center_longitude": "3.0588000",
    "radius_km": "35.00",
    "delivery_price": "250.00",
    "is_active": true
  },
  "service_city_id": 1,
  "service_city_name": "الجزائر",
  "delivery_area": {
    "id": 1,
    "service_city_id": 1,
    "name": "وسط الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_area_id": 1,
  "delivery_area_name": "وسط الجزائر",
  "delivery_area_price": "250.00",
  "delivery_type": "fixed_area",
  "delivery_price_preview": "250.00",
  "is_default": true,
  "isDefault": true,
  "created_at": "2026-07-05T07:25:39.513913Z"
}
```



### Address locations alias list

Method: `GET`  
URL: `/api/v1/locations/addresses/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 1,
    "name": "المنزل",
    "fullName": "المنزل",
    "phone": "+213555100002",
    "phoneNumber": "+213555100002",
    "line1": "المنزل",
    "street": "المنزل",
    "city": "الجزائر",
    "state": "",
    "country": "Egypt",
    "postalCode": "",
    "latitude": "36.7525000",
    "longitude": "3.0419000",
    "details": "",
    "manual_city": null,
    "manual_area": null,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "center_latitude": "36.7538000",
      "center_longitude": "3.0588000",
      "radius_km": "35.00",
      "delivery_price": "250.00",
      "is_active": true
    },
    "service_city_id": 1,
    "service_city_name": "الجزائر",
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area_id": 1,
    "delivery_area_name": "وسط الجزائر",
    "delivery_area_price": "250.00",
    "delivery_type": "fixed_area",
    "delivery_price_preview": "250.00",
    "is_default": true,
    "isDefault": true,
    "created_at": "2026-07-05T07:25:39.513913Z"
  },
  "... 2 more item(s)"
]
```



### Address update

Method: `PATCH`  
URL: `/api/v1/addresses/10/`  
Auth: Client token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "line1": "Doc Street Updated",
  "name": "Doc Address Updated",
  "service_city_id": 1,
  "delivery_area_id": 1
}
```

Response body:

```json
[
  {
    "id": 1,
    "name": "المنزل",
    "fullName": "المنزل",
    "phone": "+213555100002",
    "phoneNumber": "+213555100002",
    "line1": "المنزل",
    "street": "المنزل",
    "city": "الجزائر",
    "state": "",
    "country": "Egypt",
    "postalCode": "",
    "latitude": "36.7525000",
    "longitude": "3.0419000",
    "details": "",
    "manual_city": null,
    "manual_area": null,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "center_latitude": "36.7538000",
      "center_longitude": "3.0588000",
      "radius_km": "35.00",
      "delivery_price": "250.00",
      "is_active": true
    },
    "service_city_id": 1,
    "service_city_name": "الجزائر",
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area_id": 1,
    "delivery_area_name": "وسط الجزائر",
    "delivery_area_price": "250.00",
    "delivery_type": "fixed_area",
    "delivery_price_preview": "250.00",
    "is_default": true,
    "isDefault": true,
    "created_at": "2026-07-05T07:25:39.513913Z"
  },
  "... 2 more item(s)"
]
```



### Set default address

Method: `PATCH`  
URL: `/api/v1/addresses/10/default/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 10,
    "name": "Doc Address Updated",
    "fullName": "Doc Address Updated",
    "phone": "+213555100002",
    "phoneNumber": "+213555100002",
    "line1": "Doc Street Updated",
    "street": "Doc Street Updated",
    "city": "الجزائر",
    "state": "",
    "country": "Egypt",
    "postalCode": "",
    "latitude": null,
    "longitude": null,
    "details": "Doc Street Updated",
    "manual_city": null,
    "manual_area": null,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "center_latitude": "36.7538000",
      "center_longitude": "3.0588000",
      "radius_km": "35.00",
      "delivery_price": "250.00",
      "is_active": true
    },
    "service_city_id": 1,
    "service_city_name": "الجزائر",
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area_id": 1,
    "delivery_area_name": "وسط الجزائر",
    "delivery_area_price": "250.00",
    "delivery_type": "fixed_area",
    "delivery_price_preview": "250.00",
    "is_default": true,
    "isDefault": true,
    "created_at": "2026-07-05T07:25:57.112118Z"
  },
  "... 2 more item(s)"
]
```



### Address delete

Method: `DELETE`  
URL: `/api/v1/addresses/10/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 2,
    "name": "العمل",
    "fullName": "العمل",
    "phone": "+213555100002",
    "phoneNumber": "+213555100002",
    "line1": "العمل",
    "street": "العمل",
    "city": "الجزائر",
    "state": "",
    "country": "Egypt",
    "postalCode": "",
    "latitude": "36.7110000",
    "longitude": "3.1810000",
    "details": "",
    "manual_city": null,
    "manual_area": null,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "center_latitude": "36.7538000",
      "center_longitude": "3.0588000",
      "radius_km": "35.00",
      "delivery_price": "250.00",
      "is_active": true
    },
    "service_city_id": 1,
    "service_city_name": "الجزائر",
    "delivery_area": {
      "id": 2,
      "service_city_id": 1,
      "name": "باب الزوار",
      "delivery_price": "300.00",
      "is_active": true
    },
    "delivery_area_id": 2,
    "delivery_area_name": "باب الزوار",
    "delivery_area_price": "300.00",
    "delivery_type": "fixed_area",
    "delivery_price_preview": "300.00",
    "is_default": true,
    "isDefault": true,
    "created_at": "2026-07-05T07:25:39.516567Z"
  },
  "... 1 more item(s)"
]
```



## Orders

### Order preview

Method: `POST`  
URL: `/api/v1/orders/preview/`  
Auth: Client token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "address_id": 1,
  "items": [
    {
      "variant_id": 15,
      "quantity": 1
    }
  ],
  "offers": [
    {
      "offer_id": 10
    }
  ]
}
```

Response body:

```json
{
  "addresses": [
    {
      "id": 2,
      "name": "العمل",
      "latitude": "36.7110000",
      "longitude": "3.1810000",
      "manual_city": null,
      "manual_area": null,
      "service_city": {
        "id": 1,
        "name": "الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      },
      "service_city_id": 1,
      "delivery_area": {
        "id": 2,
        "service_city_id": 1,
        "name": "باب الزوار",
        "delivery_price": "300.00",
        "is_active": true
      },
      "delivery_area_id": 2,
      "delivery_type": "fixed_area",
      "delivery_price_preview": "300.00",
      "is_default": true,
      "created_at": "2026-07-05T07:25:39.516567Z"
    },
    "... 1 more item(s)"
  ],
  "selected_address": {
    "id": 1,
    "name": "المنزل",
    "latitude": "36.7525000",
    "longitude": "3.0419000",
    "manual_city": null,
    "manual_area": null,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "service_city_id": 1,
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area_id": 1,
    "delivery_type": "fixed_area",
    "delivery_price_preview": "250.00",
    "is_default": false,
    "created_at": "2026-07-05T07:25:39.513913Z"
  },
  "service_city": {
    "id": 1,
    "name": "الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "market_groups": [
    {
      "market": {
        "id": 2,
        "name": "مطبخ أطلس العائلي",
        "branch": "باب الزوار"
      },
      "service_city": {
        "id": 1,
        "name": "الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      },
      "delivery_area": {
        "id": 1,
        "service_city_id": 1,
        "name": "وسط الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      },
      "delivery_type": "fixed_area",
      "delivery_price": "250.00",
      "delivery_message": "",
      "delivery_available": true,
      "selected_products": [
        {
          "variant_id": 15,
          "product_id": 8,
          "product_name": "دجاج مشوي",
          "image": null,
          "quantity": 1,
          "unit_price": "980.00",
          "subtotal": "980.00"
        }
      ],
      "selected_offers": [
        {
          "id": 10,
          "title": "Doc Offer Updated",
          "description": "Doc offer",
          "image": null,
          "type": "flash",
          "discount_percentage": "5.00",
          "offer_products_subtotal": "980.00",
          "discount_amount": "49.00",
          "products": [
            {
              "product_id": 8,
              "product_name": "دجاج مشوي",
              "image": null,
              "variant_id": 15,
              "quantity": 1,
              "unit_price": "980.00",
              "subtotal": "980.00",
              "is_selected": true
            }
          ]
        }
      ],
      "pricing": {
        "products_subtotal": "980.00",
        "total_offer_discounts": "49.00",
        "delivery_price": "250.00",
        "market_total": "1181.00"
      }
    }
  ],
  "summary": {
    "subtotal": "980.00",
    "discount_total": "49.00",
    "delivery_total": "250.00",
    "grand_total": "1181.00"
  }
}
```



### Client order create

Method: `POST`  
URL: `/api/v1/orders/create/`  
Auth: Client token  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "address_id": 1,
  "payment_method": "cash",
  "description": "Client doc order",
  "delivery_note": "Call me",
  "items": [
    {
      "variant_id": 15,
      "quantity": 1
    }
  ],
  "offers": [
    {
      "offer_id": 10
    }
  ]
}
```

Response body:

```json
[
  {
    "id": 8,
    "user_id": 2,
    "customer": {
      "id": 2,
      "name": "أمينة بن سالم",
      "phone": "+213555100002"
    },
    "delivery_address_id": 1,
    "delivery_address": {
      "id": 1,
      "name": "المنزل",
      "details": "",
      "latitude": 36.7525,
      "longitude": 3.0419,
      "manual_city": null,
      "manual_area": null,
      "service_city": {
        "id": 1,
        "name": "الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      },
      "delivery_area": {
        "id": 1,
        "service_city_id": 1,
        "name": "وسط الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      },
      "delivery_type": "fixed_area",
      "delivery_price_preview": "250.00"
    },
    "assigned_representative_id": null,
    "market_id": 2,
    "market": {
      "id": 2,
      "name": "مطبخ أطلس العائلي",
      "branch": "باب الزوار",
      "status": "active"
    },
    "service_city_id": 1,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area_id": 1,
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_type": "fixed_area",
    "payment_method": "cash",
    "discount": "49.00",
    "description": "Client doc order",
    "status": "pending",
    "review_status": "pending_review",
    "delivery_price": "250.00",
    "subtotal_price": "980.00",
    "total_price": "1181.00",
    "image": null,
    "assigned_at": null,
    "delivered_at": null,
    "delivery_note": "Call me",
    "delivery_proof": null,
    "approved_by": null,
    "approved_at": null,
    "rejected_by": null,
    "rejected_at": null,
    "rejection_reason": "",
    "items": [
      {
        "id": 13,
        "variant_id": 15,
        "quantity": 1,
        "unit_price": "980.00"
      }
    ],
    "offers": [
      {
        "id": 8,
        "offer_id": 10,
        "discount_amount": "49.00",
        "created_at": "2026-07-05T07:25:57.438190Z"
      }
    ],
    "created_at": "2026-07-05T07:25:57.436112Z",
    "updated_at": "2026-07-05T07:25:57.436149Z"
  }
]
```



### Client my orders

Method: `GET`  
URL: `/api/v1/orders/my/`  
Auth: Client token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 8,
    "user_id": 2,
    "customer": {
      "id": 2,
      "name": "أمينة بن سالم",
      "phone": "+213555100002"
    },
    "delivery_address_id": 1,
    "delivery_address": {
      "id": 1,
      "name": "المنزل",
      "details": "",
      "latitude": 36.7525,
      "longitude": 3.0419,
      "manual_city": null,
      "manual_area": null,
      "service_city": {
        "id": 1,
        "name": "الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      },
      "delivery_area": {
        "id": 1,
        "service_city_id": 1,
        "name": "وسط الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      },
      "delivery_type": "fixed_area",
      "delivery_price_preview": "250.00"
    },
    "assigned_representative_id": null,
    "market_id": 2,
    "market": {
      "id": 2,
      "name": "مطبخ أطلس العائلي",
      "branch": "باب الزوار",
      "status": "active"
    },
    "service_city_id": 1,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area_id": 1,
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_type": "fixed_area",
    "payment_method": "cash",
    "discount": "49.00",
    "description": "Client doc order",
    "status": "pending",
    "review_status": "pending_review",
    "delivery_price": "250.00",
    "subtotal_price": "980.00",
    "total_price": "1181.00",
    "image": null,
    "assigned_at": null,
    "delivered_at": null,
    "delivery_note": "Call me",
    "delivery_proof": null,
    "approved_by": null,
    "approved_at": null,
    "rejected_by": null,
    "rejected_at": null,
    "rejection_reason": "",
    "items": [
      {
        "id": 13,
        "variant_id": 15,
        "quantity": 1,
        "unit_price": "980.00"
      }
    ],
    "offers": [
      {
        "id": 8,
        "offer_id": 10,
        "discount_amount": "49.00",
        "created_at": "2026-07-05T07:25:57.438190Z"
      }
    ],
    "created_at": "2026-07-05T07:25:57.436112Z",
    "updated_at": "2026-07-05T07:25:57.436149Z"
  },
  "... 2 more item(s)"
]
```



### Admin order create

Method: `POST`  
URL: `/api/v1/orders/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "user_id": 2,
  "delivery_address_id": 1,
  "market_id": 2,
  "service_city_id": 1,
  "payment_method": "cash",
  "description": "Admin doc order",
  "delivery_note": "Admin note",
  "items": [
    {
      "variant_id": 15,
      "quantity": 2,
      "unit_price": "10.00"
    }
  ],
  "offers": [
    {
      "offer_id": 10,
      "discount_amount": "3.00"
    }
  ]
}
```

Response body:

```json
{
  "id": 9,
  "user_id": 2,
  "customer": {
    "id": 2,
    "name": "أمينة بن سالم",
    "phone": "+213555100002"
  },
  "delivery_address_id": 1,
  "delivery_address": {
    "id": 1,
    "name": "المنزل",
    "details": "",
    "latitude": 36.7525,
    "longitude": 3.0419,
    "manual_city": null,
    "manual_area": null,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_type": "fixed_area",
    "delivery_price_preview": "250.00"
  },
  "assigned_representative_id": null,
  "market_id": 2,
  "market": {
    "id": 2,
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "status": "active"
  },
  "service_city_id": 1,
  "service_city": {
    "id": 1,
    "name": "الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_area_id": 1,
  "delivery_area": {
    "id": 1,
    "service_city_id": 1,
    "name": "وسط الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_type": "fixed_area",
  "payment_method": "cash",
  "discount": "3.00",
  "description": "Admin doc order",
  "status": "pending",
  "review_status": "pending_review",
  "delivery_price": "250.00",
  "subtotal_price": "20.00",
  "total_price": "267.00",
  "image": null,
  "assigned_at": null,
  "delivered_at": null,
  "delivery_note": "Admin note",
  "delivery_proof": null,
  "approved_by": null,
  "approved_at": null,
  "rejected_by": null,
  "rejected_at": null,
  "rejection_reason": "",
  "items": [
    {
      "id": 14,
      "variant_id": 15,
      "quantity": 2,
      "unit_price": "10.00"
    }
  ],
  "offers": [
    {
      "id": 9,
      "offer_id": 10,
      "discount_amount": "3.00",
      "created_at": "2026-07-05T07:25:57.567865Z"
    }
  ],
  "created_at": "2026-07-05T07:25:57.564803Z",
  "updated_at": "2026-07-05T07:25:57.564867Z"
}
```



### Admin order list

Method: `GET`  
URL: `/api/v1/orders/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 9,
    "user_id": 2,
    "customer": {
      "id": 2,
      "name": "أمينة بن سالم",
      "phone": "+213555100002"
    },
    "delivery_address_id": 1,
    "delivery_address": {
      "id": 1,
      "name": "المنزل",
      "details": "",
      "latitude": 36.7525,
      "longitude": 3.0419,
      "manual_city": null,
      "manual_area": null,
      "service_city": {
        "id": 1,
        "name": "الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      },
      "delivery_area": {
        "id": 1,
        "service_city_id": 1,
        "name": "وسط الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      },
      "delivery_type": "fixed_area",
      "delivery_price_preview": "250.00"
    },
    "assigned_representative_id": null,
    "market_id": 2,
    "market": {
      "id": 2,
      "name": "مطبخ أطلس العائلي",
      "branch": "باب الزوار",
      "status": "active"
    },
    "service_city_id": 1,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area_id": 1,
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_type": "fixed_area",
    "payment_method": "cash",
    "discount": "3.00",
    "description": "Admin doc order",
    "status": "pending",
    "review_status": "pending_review",
    "delivery_price": "250.00",
    "subtotal_price": "20.00",
    "total_price": "267.00",
    "image": null,
    "assigned_at": null,
    "delivered_at": null,
    "delivery_note": "Admin note",
    "delivery_proof": null,
    "approved_by": null,
    "approved_at": null,
    "rejected_by": null,
    "rejected_at": null,
    "rejection_reason": "",
    "items": [
      {
        "id": 14,
        "variant_id": 15,
        "quantity": 2,
        "unit_price": "10.00"
      }
    ],
    "offers": [
      {
        "id": 9,
        "offer_id": 10,
        "discount_amount": "3.00",
        "created_at": "2026-07-05T07:25:57.567865Z"
      }
    ],
    "created_at": "2026-07-05T07:25:57.564803Z",
    "updated_at": "2026-07-05T07:25:57.564867Z"
  },
  "... 8 more item(s)"
]
```



### Admin order detail

Method: `GET`  
URL: `/api/v1/orders/9/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": 9,
  "user_id": 2,
  "customer": {
    "id": 2,
    "name": "أمينة بن سالم",
    "phone": "+213555100002"
  },
  "delivery_address_id": 1,
  "delivery_address": {
    "id": 1,
    "name": "المنزل",
    "details": "",
    "latitude": 36.7525,
    "longitude": 3.0419,
    "manual_city": null,
    "manual_area": null,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_type": "fixed_area",
    "delivery_price_preview": "250.00"
  },
  "assigned_representative_id": null,
  "market_id": 2,
  "market": {
    "id": 2,
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "status": "active"
  },
  "service_city_id": 1,
  "service_city": {
    "id": 1,
    "name": "الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_area_id": 1,
  "delivery_area": {
    "id": 1,
    "service_city_id": 1,
    "name": "وسط الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_type": "fixed_area",
  "payment_method": "cash",
  "discount": "3.00",
  "description": "Admin doc order",
  "status": "pending",
  "review_status": "pending_review",
  "delivery_price": "250.00",
  "subtotal_price": "20.00",
  "total_price": "267.00",
  "image": null,
  "assigned_at": null,
  "delivered_at": null,
  "delivery_note": "Admin note",
  "delivery_proof": null,
  "approved_by": null,
  "approved_at": null,
  "rejected_by": null,
  "rejected_at": null,
  "rejection_reason": "",
  "items": [
    {
      "id": 14,
      "variant_id": 15,
      "quantity": 2,
      "unit_price": "10.00"
    }
  ],
  "offers": [
    {
      "id": 9,
      "offer_id": 10,
      "discount_amount": "3.00",
      "created_at": "2026-07-05T07:25:57.567865Z"
    }
  ],
  "created_at": "2026-07-05T07:25:57.564803Z",
  "updated_at": "2026-07-05T07:25:57.564867Z"
}
```



### Admin order status update

Method: `PATCH`  
URL: `/api/v1/orders/9/status/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "status": "under_preparation"
}
```

Response body:

```json
{
  "id": 9,
  "user_id": 2,
  "customer": {
    "id": 2,
    "name": "أمينة بن سالم",
    "phone": "+213555100002"
  },
  "delivery_address_id": 1,
  "delivery_address": {
    "id": 1,
    "name": "المنزل",
    "details": "",
    "latitude": 36.7525,
    "longitude": 3.0419,
    "manual_city": null,
    "manual_area": null,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_type": "fixed_area",
    "delivery_price_preview": "250.00"
  },
  "assigned_representative_id": null,
  "market_id": 2,
  "market": {
    "id": 2,
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "status": "active"
  },
  "service_city_id": 1,
  "service_city": {
    "id": 1,
    "name": "الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_area_id": 1,
  "delivery_area": {
    "id": 1,
    "service_city_id": 1,
    "name": "وسط الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_type": "fixed_area",
  "payment_method": "cash",
  "discount": "3.00",
  "description": "Admin doc order",
  "status": "under_preparation",
  "review_status": "pending_review",
  "delivery_price": "250.00",
  "subtotal_price": "20.00",
  "total_price": "267.00",
  "image": null,
  "assigned_at": null,
  "delivered_at": null,
  "delivery_note": "Admin note",
  "delivery_proof": null,
  "approved_by": null,
  "approved_at": null,
  "rejected_by": null,
  "rejected_at": null,
  "rejection_reason": "",
  "items": [
    {
      "id": 14,
      "variant_id": 15,
      "quantity": 2,
      "unit_price": "10.00"
    }
  ],
  "offers": [
    {
      "id": 9,
      "offer_id": 10,
      "discount_amount": "3.00",
      "created_at": "2026-07-05T07:25:57.567865Z"
    }
  ],
  "created_at": "2026-07-05T07:25:57.564803Z",
  "updated_at": "2026-07-05T07:25:57.709969Z"
}
```



### Admin order replace

Method: `PUT`  
URL: `/api/v1/orders/9/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "user_id": 2,
  "delivery_address_id": 1,
  "market_id": 2,
  "service_city_id": 1,
  "delivery_area_id": 1,
  "delivery_type": "fixed_area",
  "payment_method": "cash",
  "description": "Admin doc order replaced",
  "delivery_note": "PUT note",
  "discount": "3.00",
  "status": "pending",
  "delivery_price": "250.00",
  "subtotal_price": "20.00",
  "total_price": "267.00",
  "items": [
    {
      "variant_id": 15,
      "quantity": 2,
      "unit_price": "10.00"
    }
  ],
  "offers": [
    {
      "offer_id": 10,
      "discount_amount": "3.00"
    }
  ]
}
```

Response body:

```json
{
  "id": 9,
  "user_id": 2,
  "customer": {
    "id": 2,
    "name": "أمينة بن سالم",
    "phone": "+213555100002"
  },
  "delivery_address_id": 1,
  "delivery_address": {
    "id": 1,
    "name": "المنزل",
    "details": "",
    "latitude": 36.7525,
    "longitude": 3.0419,
    "manual_city": null,
    "manual_area": null,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_type": "fixed_area",
    "delivery_price_preview": "250.00"
  },
  "assigned_representative_id": null,
  "market_id": 2,
  "market": {
    "id": 2,
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "status": "active"
  },
  "service_city_id": 1,
  "service_city": {
    "id": 1,
    "name": "الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_area_id": 1,
  "delivery_area": {
    "id": 1,
    "service_city_id": 1,
    "name": "وسط الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_type": "fixed_area",
  "payment_method": "cash",
  "discount": "3.00",
  "description": "Admin doc order replaced",
  "status": "pending",
  "review_status": "pending_review",
  "delivery_price": "250.00",
  "subtotal_price": "20.00",
  "total_price": "267.00",
  "image": null,
  "assigned_at": null,
  "delivered_at": null,
  "delivery_note": "PUT note",
  "delivery_proof": null,
  "approved_by": null,
  "approved_at": null,
  "rejected_by": null,
  "rejected_at": null,
  "rejection_reason": "",
  "items": [
    {
      "id": 15,
      "variant_id": 15,
      "quantity": 2,
      "unit_price": "10.00"
    }
  ],
  "offers": [
    {
      "id": 10,
      "offer_id": 10,
      "discount_amount": "3.00",
      "created_at": "2026-07-05T07:25:57.788336Z"
    }
  ],
  "created_at": "2026-07-05T07:25:57.564803Z",
  "updated_at": "2026-07-05T07:25:57.784575Z"
}
```



### Admin order patch detail

Method: `PATCH`  
URL: `/api/v1/orders/9/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "description": "Admin doc order patched"
}
```

Response body:

```json
{
  "id": 9,
  "user_id": 2,
  "customer": {
    "id": 2,
    "name": "أمينة بن سالم",
    "phone": "+213555100002"
  },
  "delivery_address_id": 1,
  "delivery_address": {
    "id": 1,
    "name": "المنزل",
    "details": "",
    "latitude": 36.7525,
    "longitude": 3.0419,
    "manual_city": null,
    "manual_area": null,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_type": "fixed_area",
    "delivery_price_preview": "250.00"
  },
  "assigned_representative_id": null,
  "market_id": 2,
  "market": {
    "id": 2,
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "status": "active"
  },
  "service_city_id": 1,
  "service_city": {
    "id": 1,
    "name": "الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_area_id": 1,
  "delivery_area": {
    "id": 1,
    "service_city_id": 1,
    "name": "وسط الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_type": "fixed_area",
  "payment_method": "cash",
  "discount": "3.00",
  "description": "Admin doc order patched",
  "status": "pending",
  "review_status": "pending_review",
  "delivery_price": "250.00",
  "subtotal_price": "20.00",
  "total_price": "267.00",
  "image": null,
  "assigned_at": null,
  "delivered_at": null,
  "delivery_note": "PUT note",
  "delivery_proof": null,
  "approved_by": null,
  "approved_at": null,
  "rejected_by": null,
  "rejected_at": null,
  "rejection_reason": "",
  "items": [
    {
      "id": 15,
      "variant_id": 15,
      "quantity": 2,
      "unit_price": "10.00"
    }
  ],
  "offers": [
    {
      "id": 10,
      "offer_id": 10,
      "discount_amount": "3.00",
      "created_at": "2026-07-05T07:25:57.788336Z"
    }
  ],
  "created_at": "2026-07-05T07:25:57.564803Z",
  "updated_at": "2026-07-05T07:25:57.840259Z"
}
```



### Admin order delete cancel

Method: `DELETE`  
URL: `/api/v1/orders/9/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": 9,
  "user_id": 2,
  "customer": {
    "id": 2,
    "name": "أمينة بن سالم",
    "phone": "+213555100002"
  },
  "delivery_address_id": 1,
  "delivery_address": {
    "id": 1,
    "name": "المنزل",
    "details": "",
    "latitude": 36.7525,
    "longitude": 3.0419,
    "manual_city": null,
    "manual_area": null,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_type": "fixed_area",
    "delivery_price_preview": "250.00"
  },
  "assigned_representative_id": null,
  "market_id": 2,
  "market": {
    "id": 2,
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "status": "active"
  },
  "service_city_id": 1,
  "service_city": {
    "id": 1,
    "name": "الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_area_id": 1,
  "delivery_area": {
    "id": 1,
    "service_city_id": 1,
    "name": "وسط الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_type": "fixed_area",
  "payment_method": "cash",
  "discount": "3.00",
  "description": "Admin doc order patched",
  "status": "cancelled",
  "review_status": "pending_review",
  "delivery_price": "250.00",
  "subtotal_price": "20.00",
  "total_price": "267.00",
  "image": null,
  "assigned_at": null,
  "delivered_at": null,
  "delivery_note": "PUT note",
  "delivery_proof": null,
  "approved_by": null,
  "approved_at": null,
  "rejected_by": null,
  "rejected_at": null,
  "rejection_reason": "",
  "items": [
    {
      "id": 15,
      "variant_id": 15,
      "quantity": 2,
      "unit_price": "10.00"
    }
  ],
  "offers": [
    {
      "id": 10,
      "offer_id": 10,
      "discount_amount": "3.00",
      "created_at": "2026-07-05T07:25:57.788336Z"
    }
  ],
  "created_at": "2026-07-05T07:25:57.564803Z",
  "updated_at": "2026-07-05T07:25:57.886189Z"
}
```



### Admin order create for assignment

Method: `POST`  
URL: `/api/v1/orders/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "user_id": 2,
  "delivery_address_id": 1,
  "market_id": 2,
  "service_city_id": 1,
  "payment_method": "cash",
  "description": "Assign doc order",
  "delivery_note": "Admin note",
  "items": [
    {
      "variant_id": 15,
      "quantity": 2,
      "unit_price": "10.00"
    }
  ],
  "offers": [
    {
      "offer_id": 10,
      "discount_amount": "3.00"
    }
  ]
}
```

Response body:

```json
{
  "id": 10,
  "user_id": 2,
  "customer": {
    "id": 2,
    "name": "أمينة بن سالم",
    "phone": "+213555100002"
  },
  "delivery_address_id": 1,
  "delivery_address": {
    "id": 1,
    "name": "المنزل",
    "details": "",
    "latitude": 36.7525,
    "longitude": 3.0419,
    "manual_city": null,
    "manual_area": null,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_type": "fixed_area",
    "delivery_price_preview": "250.00"
  },
  "assigned_representative_id": null,
  "market_id": 2,
  "market": {
    "id": 2,
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "status": "active"
  },
  "service_city_id": 1,
  "service_city": {
    "id": 1,
    "name": "الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_area_id": 1,
  "delivery_area": {
    "id": 1,
    "service_city_id": 1,
    "name": "وسط الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_type": "fixed_area",
  "payment_method": "cash",
  "discount": "3.00",
  "description": "Assign doc order",
  "status": "pending",
  "review_status": "pending_review",
  "delivery_price": "250.00",
  "subtotal_price": "20.00",
  "total_price": "267.00",
  "image": null,
  "assigned_at": null,
  "delivered_at": null,
  "delivery_note": "Admin note",
  "delivery_proof": null,
  "approved_by": null,
  "approved_at": null,
  "rejected_by": null,
  "rejected_at": null,
  "rejection_reason": "",
  "items": [
    {
      "id": 16,
      "variant_id": 15,
      "quantity": 2,
      "unit_price": "10.00"
    }
  ],
  "offers": [
    {
      "id": 11,
      "offer_id": 10,
      "discount_amount": "3.00",
      "created_at": "2026-07-05T07:25:57.937058Z"
    }
  ],
  "created_at": "2026-07-05T07:25:57.934952Z",
  "updated_at": "2026-07-05T07:25:57.934997Z"
}
```



### Assign order

Method: `PATCH`  
URL: `/api/v1/orders/10/assignment/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "representative_id": 4
}
```

Response body:

```json
{
  "message": "Order assigned successfully.",
  "order": {
    "id": 10,
    "user_id": 2,
    "customer": {
      "id": 2,
      "name": "أمينة بن سالم",
      "phone": "+213555100002"
    },
    "delivery_address_id": 1,
    "delivery_address": {
      "id": 1,
      "name": "المنزل",
      "details": "",
      "latitude": 36.7525,
      "longitude": 3.0419,
      "manual_city": null,
      "manual_area": null,
      "service_city": {
        "id": 1,
        "name": "الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      },
      "delivery_area": {
        "id": 1,
        "service_city_id": 1,
        "name": "وسط الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      },
      "delivery_type": "fixed_area",
      "delivery_price_preview": "250.00"
    },
    "assigned_representative_id": 4,
    "market_id": 2,
    "market": {
      "id": 2,
      "name": "مطبخ أطلس العائلي",
      "branch": "باب الزوار",
      "status": "active"
    },
    "service_city_id": 1,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area_id": 1,
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_type": "fixed_area",
    "payment_method": "cash",
    "discount": "3.00",
    "description": "Assign doc order",
    "status": "ready",
    "review_status": "approved",
    "delivery_price": "250.00",
    "subtotal_price": "20.00",
    "total_price": "267.00",
    "image": null,
    "assigned_at": "2026-07-05T07:25:58.087344Z",
    "delivered_at": null,
    "delivery_note": "Admin note",
    "delivery_proof": null,
    "approved_by": 1,
    "approved_at": "2026-07-05T07:25:58.018243Z",
    "rejected_by": null,
    "rejected_at": null,
    "rejection_reason": "",
    "items": [
      {
        "id": 16,
        "variant_id": 15,
        "quantity": 2,
        "unit_price": "10.00"
      }
    ],
    "offers": [
      {
        "id": 11,
        "offer_id": 10,
        "discount_amount": "3.00",
        "created_at": "2026-07-05T07:25:57.937058Z"
      }
    ],
    "created_at": "2026-07-05T07:25:57.934952Z",
    "updated_at": "2026-07-05T07:25:58.087495Z"
  },
  "representative": {
    "representative_id": 4,
    "user_id": 4,
    "name": "سفيان مندوب",
    "phone": "+213555100004",
    "service_city_id": 1,
    "service_city": "الجزائر"
  }
}
```



### Admin order create for rejection

Method: `POST`  
URL: `/api/v1/orders/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `201`


Request body:

```json
{
  "user_id": 2,
  "delivery_address_id": 1,
  "market_id": 2,
  "service_city_id": 1,
  "payment_method": "cash",
  "description": "Reject doc order",
  "delivery_note": "Admin note",
  "items": [
    {
      "variant_id": 15,
      "quantity": 2,
      "unit_price": "10.00"
    }
  ],
  "offers": [
    {
      "offer_id": 10,
      "discount_amount": "3.00"
    }
  ]
}
```

Response body:

```json
{
  "id": 11,
  "user_id": 2,
  "customer": {
    "id": 2,
    "name": "أمينة بن سالم",
    "phone": "+213555100002"
  },
  "delivery_address_id": 1,
  "delivery_address": {
    "id": 1,
    "name": "المنزل",
    "details": "",
    "latitude": 36.7525,
    "longitude": 3.0419,
    "manual_city": null,
    "manual_area": null,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_type": "fixed_area",
    "delivery_price_preview": "250.00"
  },
  "assigned_representative_id": null,
  "market_id": 2,
  "market": {
    "id": 2,
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "status": "active"
  },
  "service_city_id": 1,
  "service_city": {
    "id": 1,
    "name": "الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_area_id": 1,
  "delivery_area": {
    "id": 1,
    "service_city_id": 1,
    "name": "وسط الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_type": "fixed_area",
  "payment_method": "cash",
  "discount": "3.00",
  "description": "Reject doc order",
  "status": "pending",
  "review_status": "pending_review",
  "delivery_price": "250.00",
  "subtotal_price": "20.00",
  "total_price": "267.00",
  "image": null,
  "assigned_at": null,
  "delivered_at": null,
  "delivery_note": "Admin note",
  "delivery_proof": null,
  "approved_by": null,
  "approved_at": null,
  "rejected_by": null,
  "rejected_at": null,
  "rejection_reason": "",
  "items": [
    {
      "id": 17,
      "variant_id": 15,
      "quantity": 2,
      "unit_price": "10.00"
    }
  ],
  "offers": [
    {
      "id": 12,
      "offer_id": 10,
      "discount_amount": "3.00",
      "created_at": "2026-07-05T07:25:58.266459Z"
    }
  ],
  "created_at": "2026-07-05T07:25:58.263918Z",
  "updated_at": "2026-07-05T07:25:58.263955Z"
}
```



## Orders Admin Review

### Order review blocker

Method: `GET`  
URL: `/api/v1/admin/order-review/blocker/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "blocked": true,
  "pending_count": 3,
  "orders": [
    {
      "id": 10,
      "user_id": 2,
      "customer": {
        "id": 2,
        "name": "أمينة بن سالم",
        "phone": "+213555100002"
      },
      "delivery_address_id": 1,
      "delivery_address": {
        "id": 1,
        "name": "المنزل",
        "details": "",
        "latitude": 36.7525,
        "longitude": 3.0419,
        "manual_city": null,
        "manual_area": null,
        "service_city": {
          "id": 1,
          "name": "الجزائر",
          "delivery_price": "250.00",
          "is_active": true
        },
        "delivery_area": {
          "id": 1,
          "service_city_id": 1,
          "name": "وسط الجزائر",
          "delivery_price": "250.00",
          "is_active": true
        },
        "delivery_type": "fixed_area",
        "delivery_price_preview": "250.00"
      },
      "assigned_representative_id": null,
      "market_id": 2,
      "market": {
        "id": 2,
        "name": "مطبخ أطلس العائلي",
        "branch": "باب الزوار",
        "status": "active"
      },
      "service_city_id": 1,
      "service_city": {
        "id": 1,
        "name": "الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      },
      "delivery_area_id": 1,
      "delivery_area": {
        "id": 1,
        "service_city_id": 1,
        "name": "وسط الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      },
      "delivery_type": "fixed_area",
      "payment_method": "cash",
      "discount": "3.00",
      "description": "Assign doc order",
      "status": "pending",
      "review_status": "pending_review",
      "delivery_price": "250.00",
      "subtotal_price": "20.00",
      "total_price": "267.00",
      "image": null,
      "assigned_at": null,
      "delivered_at": null,
      "delivery_note": "Admin note",
      "delivery_proof": null,
      "approved_by": null,
      "approved_at": null,
      "rejected_by": null,
      "rejected_at": null,
      "rejection_reason": "",
      "items": [
        {
          "id": 16,
          "variant_id": 15,
          "quantity": 2,
          "unit_price": "10.00"
        }
      ],
      "offers": [
        {
          "id": 11,
          "offer_id": 10,
          "discount_amount": "3.00",
          "created_at": "2026-07-05T07:25:57.937058Z"
        }
      ],
      "created_at": "2026-07-05T07:25:57.934952Z",
      "updated_at": "2026-07-05T07:25:57.934997Z"
    },
    "... 2 more item(s)"
  ]
}
```



### Approve order

Method: `POST`  
URL: `/api/v1/admin/orders/10/approve/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{}
```

Response body:

```json
{
  "message": "Order approved successfully.",
  "order": {
    "id": 10,
    "user_id": 2,
    "customer": {
      "id": 2,
      "name": "أمينة بن سالم",
      "phone": "+213555100002"
    },
    "delivery_address_id": 1,
    "delivery_address": {
      "id": 1,
      "name": "المنزل",
      "details": "",
      "latitude": 36.7525,
      "longitude": 3.0419,
      "manual_city": null,
      "manual_area": null,
      "service_city": {
        "id": 1,
        "name": "الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      },
      "delivery_area": {
        "id": 1,
        "service_city_id": 1,
        "name": "وسط الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      },
      "delivery_type": "fixed_area",
      "delivery_price_preview": "250.00"
    },
    "assigned_representative_id": null,
    "market_id": 2,
    "market": {
      "id": 2,
      "name": "مطبخ أطلس العائلي",
      "branch": "باب الزوار",
      "status": "active"
    },
    "service_city_id": 1,
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area_id": 1,
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_type": "fixed_area",
    "payment_method": "cash",
    "discount": "3.00",
    "description": "Assign doc order",
    "status": "under_preparation",
    "review_status": "approved",
    "delivery_price": "250.00",
    "subtotal_price": "20.00",
    "total_price": "267.00",
    "image": null,
    "assigned_at": null,
    "delivered_at": null,
    "delivery_note": "Admin note",
    "delivery_proof": null,
    "approved_by": 1,
    "approved_at": "2026-07-05T07:25:58.018243Z",
    "rejected_by": null,
    "rejected_at": null,
    "rejection_reason": "",
    "items": [
      {
        "id": 16,
        "variant_id": 15,
        "quantity": 2,
        "unit_price": "10.00"
      }
    ],
    "offers": [
      {
        "id": 11,
        "offer_id": 10,
        "discount_amount": "3.00",
        "created_at": "2026-07-05T07:25:57.937058Z"
      }
    ],
    "created_at": "2026-07-05T07:25:57.934952Z",
    "updated_at": "2026-07-05T07:25:58.018431Z"
  },
  "service_city": {
    "id": 1,
    "name": "الجزائر"
  },
  "available_representatives": [
    {
      "representative_id": 4,
      "user_id": 4,
      "name": "سفيان مندوب",
      "phone": "+213555100004",
      "service_city_id": 1,
      "service_city": "الجزائر"
    }
  ]
}
```



### Service-city representatives for order

Method: `GET`  
URL: `/api/v1/admin/orders/10/service-city-representatives/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "order_id": 10,
  "service_city": {
    "id": 1,
    "name": "الجزائر"
  },
  "representatives": [
    {
      "representative_id": 4,
      "user_id": 4,
      "name": "سفيان مندوب",
      "phone": "+213555100004",
      "service_city_id": 1,
      "service_city": "الجزائر"
    }
  ]
}
```



### Reject order

Method: `POST`  
URL: `/api/v1/admin/orders/11/reject/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "rejection_reason": "Out of stock"
}
```

Response body:

```json
{
  "message": "Order rejected successfully.",
  "order_id": 11,
  "status": "cancelled",
  "review_status": "rejected",
  "rejection_reason": "Out of stock"
}
```



## Courier

### Courier order list

Method: `GET`  
URL: `/api/v1/courier/orders/`  
Auth: Courier token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 10,
    "status": "ready",
    "service_city": {
      "id": 1,
      "name": "الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_type": "fixed_area",
    "market": {
      "id": 2,
      "name": "مطبخ أطلس العائلي",
      "branch": "باب الزوار",
      "status": "active"
    },
    "customer": {
      "id": 2,
      "name": "أمينة بن سالم",
      "phone": "+213555100002"
    },
    "delivery_address": {
      "id": 1,
      "name": "المنزل",
      "details": "",
      "delivery_area": {
        "id": 1,
        "service_city_id": 1,
        "name": "وسط الجزائر",
        "delivery_price": "250.00",
        "is_active": true
      },
      "delivery_type": "fixed_area"
    },
    "total_price": "267.00",
    "delivery_price": "250.00",
    "created_at": "2026-07-05T07:25:57.934952Z",
    "assigned_at": "2026-07-05T07:25:58.087344Z"
  },
  "... 2 more item(s)"
]
```



### Courier order detail

Method: `GET`  
URL: `/api/v1/courier/orders/10/`  
Auth: Courier token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "id": 10,
  "status": "ready",
  "service_city": {
    "id": 1,
    "name": "الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_area": {
    "id": 1,
    "service_city_id": 1,
    "name": "وسط الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_type": "fixed_area",
  "market": {
    "id": 2,
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "status": "active"
  },
  "customer": {
    "id": 2,
    "name": "أمينة بن سالم",
    "phone": "+213555100002"
  },
  "delivery_address": {
    "id": 1,
    "name": "المنزل",
    "details": "",
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_type": "fixed_area"
  },
  "total_price": "267.00",
  "delivery_price": "250.00",
  "created_at": "2026-07-05T07:25:57.934952Z",
  "assigned_at": "2026-07-05T07:25:58.087344Z",
  "items": [
    {
      "id": 16,
      "quantity": 2,
      "unit_price": "10.00",
      "product": {
        "id": 8,
        "name": "دجاج مشوي",
        "description": "منتج تجريبي: دجاج مشوي.",
        "image": null
      },
      "variant": {
        "id": 15,
        "sku": "SEED-08-1",
        "price": 980.0
      }
    }
  ],
  "offers": [
    {
      "id": 11,
      "offer": {
        "id": 10,
        "title": "Doc Offer Updated",
        "description": "Doc offer",
        "type": "flash",
        "discount": 5.0
      },
      "discount_amount": "3.00",
      "created_at": "2026-07-05T07:25:57.937058Z"
    }
  ],
  "subtotal_price": "20.00",
  "discount": "3.00",
  "delivery_note": "Admin note",
  "delivery_proof": null,
  "delivered_at": null
}
```



### Courier order status

Method: `PATCH`  
URL: `/api/v1/courier/orders/10/status/`  
Auth: Courier token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{
  "status": "picked_up"
}
```

Response body:

```json
{
  "id": 10,
  "status": "picked_up",
  "service_city": {
    "id": 1,
    "name": "الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_area": {
    "id": 1,
    "service_city_id": 1,
    "name": "وسط الجزائر",
    "delivery_price": "250.00",
    "is_active": true
  },
  "delivery_type": "fixed_area",
  "market": {
    "id": 2,
    "name": "مطبخ أطلس العائلي",
    "branch": "باب الزوار",
    "status": "active"
  },
  "customer": {
    "id": 2,
    "name": "أمينة بن سالم",
    "phone": "+213555100002"
  },
  "delivery_address": {
    "id": 1,
    "name": "المنزل",
    "details": "",
    "delivery_area": {
      "id": 1,
      "service_city_id": 1,
      "name": "وسط الجزائر",
      "delivery_price": "250.00",
      "is_active": true
    },
    "delivery_type": "fixed_area"
  },
  "total_price": "267.00",
  "delivery_price": "250.00",
  "created_at": "2026-07-05T07:25:57.934952Z",
  "assigned_at": "2026-07-05T07:25:58.087344Z",
  "items": [
    {
      "id": 16,
      "quantity": 2,
      "unit_price": "10.00",
      "product": {
        "id": 8,
        "name": "دجاج مشوي",
        "description": "منتج تجريبي: دجاج مشوي.",
        "image": null
      },
      "variant": {
        "id": 15,
        "sku": "SEED-08-1",
        "price": 980.0
      }
    }
  ],
  "offers": [
    {
      "id": 11,
      "offer": {
        "id": 10,
        "title": "Doc Offer Updated",
        "description": "Doc offer",
        "type": "flash",
        "discount": 5.0
      },
      "discount_amount": "3.00",
      "created_at": "2026-07-05T07:25:57.937058Z"
    }
  ],
  "subtotal_price": "20.00",
  "discount": "3.00",
  "delivery_note": "Admin note",
  "delivery_proof": null,
  "delivered_at": null
}
```



## Notifications

### Notifications list

Method: `GET`  
URL: `/api/v1/notifications/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
[
  {
    "id": 1,
    "audience": "admin",
    "type": "new_order_review",
    "title": "New order requires review",
    "message": "Order #8 requires admin review.",
    "order_id": 8,
    "is_read": false,
    "is_blocking": true,
    "is_resolved": false,
    "created_at": "2026-07-05T07:25:57.438990Z"
  }
]
```



### Mark notification read

Method: `PATCH`  
URL: `/api/v1/notifications/1/read/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{}
```

Response body:

```json
{
  "id": 1,
  "audience": "admin",
  "type": "new_order_review",
  "title": "New order requires review",
  "message": "Order #8 requires admin review.",
  "order_id": 8,
  "is_read": true,
  "is_blocking": true,
  "is_resolved": false,
  "created_at": "2026-07-05T07:25:57.438990Z"
}
```



### Unread notification count

Method: `GET`  
URL: `/api/v1/notifications/unread-count/`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "unread_count": 0
}
```



### Mark all notifications read

Method: `POST`  
URL: `/api/v1/notifications/mark-all-read/`  
Auth: Admin token  
Content-Type: `application/json`  
HTTP status: `200`


Request body:

```json
{}
```

Response body:

```json
{
  "marked_read": 0
}
```



## Dashboard

### Dashboard overview

Method: `GET`  
URL: `/api/v1/dashboard/overview/?from=2026-01-01&to=2026-12-31`  
Auth: Admin token  
Content-Type: `none`  
HTTP status: `200`


Request body:

```text
none
```

Response body:

```json
{
  "range": {
    "from": "2026-01-01",
    "to": "2026-12-31",
    "timezone": "UTC"
  },
  "currency": "EGP",
  "revenue": {
    "total": "2765.00",
    "percentage": 23.8
  },
  "orders": {
    "total": 11,
    "completed": 2,
    "incomplete": 9,
    "completion_rate": 18.2
  },
  "customers": {
    "new": 4,
    "returning": 0,
    "return_rate": 0.0
  },
  "top_products": [
    {
      "product_id": 1,
      "name": "تفاح أحمر",
      "revenue": "1120.00",
      "quantity_sold": 2,
      "orders_count": 1
    },
    "... 3 more item(s)"
  ],
  "active_orders": [
    {
      "id": 8,
      "number": "YM-20260705-000008",
      "customer": {
        "id": 2,
        "name": "أمينة بن سالم"
      },
      "total": "1181.00",
      "status": "pending",
      "created_at": "2026-07-05T07:25:57.436112Z"
    },
    "... 4 more item(s)"
  ],
  "top_shops": [
    {
      "market_id": 1,
      "name": "سوق يلا الطازج - وسط الجزائر",
      "zone": "الجزائر",
      "orders_count": 1,
      "average_items_per_order": 5.0,
      "revenue": "1790.00"
    },
    "... 1 more item(s)"
  ]
}
```



## Compatibility Notes

- Address endpoints exist under both `/api/v1/addresses/` and `/api/v1/locations/addresses/`; write examples use `/api/v1/addresses/`.

- Admin order create rejects system-controlled fields: `status`, `review_status`, `assigned_representative_id`, `assigned_at`, `delivered_at`, `delivery_price`, `delivery_area_id`, `delivery_type`, `subtotal_price`, `total_price`, `discount`, `image`, `delivery_proof`, `approved_by`, `approved_at`, `rejected_by`, `rejected_at`, `rejection_reason`.

- Long list responses are curl-verified but shortened to the first item plus a count marker when repeated. Object field shapes are kept intact.
