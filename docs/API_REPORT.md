# Yalla Backend API Report

آخر تحقق: 2026-07-13

مصدر التحقق: الكود الحالي، اختبارات بوقت متحكم فيه، وطلبات `curl` فعلية على خادم محلي بقاعدة SQLite مؤقتة وحسابات عميل مخصصة للاختبار.
الهدف من هذا الملف: مرجع ربط واضح للعميل، لوحة الإدارة، والمندوب. الأمثلة مأخوذة من استجابات فعلية، لكن قيم `id` والتواريخ أمثلة seed وقد تختلف بعد إعادة إنشاء البيانات.

## قواعد عامة

- كل المسارات تحت `/api/v1/`.
- استخدم `Content-Type: application/json` إلا في رفع الصور والملفات.
- المصادقة: `Authorization: Bearer <accessToken>`.
- مبالغ المال ترجع غالباً كنص عشري مثل `"180.00"`، وبعض حقول المدن القديمة ترجع رقم مثل `45.0` في اختيار المنطقة.
- قيم `null` مهمة في الربط، خصوصاً `service_city`, `delivery_area`, `delivery_price` في الطلب العام.
- بعض endpoints ترجع Array مباشرة، وبعضها يرجع object، وبعض البحث يرجع pagination `{count,next,previous,results}`.
- `/api/v1/orders/create/` للعميل يرجع **قائمة تحتوي طلب أب واحد** حتى لو فيه أكثر من محل: `[{ ...order }]`.
- النظام الحالي مصري في seed demo: أرقام `+20`، مدن مثل القاهرة والجيزة والإسكندرية. لا تعتمد على أي أمثلة قديمة تخص دول أخرى.

## بيانات دخول Demo

| الدور | Endpoint | Email | Password |
|---|---|---|---|
| Admin | `/api/v1/auth/login/admin/` | `seed.admin@yalla.seed` | `SeedPass1!` |
| Client service-city | `/api/v1/auth/login/client/` | `seed.amina@yalla.seed` | `SeedPass1!` |
| Client general | `/api/v1/auth/login/client/` | `seed.karim@yalla.seed` | `SeedPass1!` |
| Courier | `/api/v1/auth/login/representative/` | `seed.courier1@yalla.seed` | `SeedPass1!` |

## أهم القواعد للربط

- يجب اختيار `market_region` قبل عرض home/offers/search/checkout للعميل.
- `mode=general` يعني السوق العام فقط، حتى لو `manual_city` مكتوبة `القاهرة`.
- طلب `general` دائماً يطبّع التوصيل هكذا: `service_city=null`, `delivery_area=null`, `delivery_type=delivery`, `delivery_price=null`.
- عنوان طلب `general` يجب أن يكون عنواناً يدوياً عاماً: `service_city_id=null`, `delivery_area_id=null`, مع `manual_city` و`manual_area` كنص.
- طلب `service_city` يحتاج `service_city`. يستخدم `fixed_area` فقط إذا كان العنوان مربوطاً بـ `delivery_area` نشطة وتابعة لنفس المدينة، وإلا يكون `delivery_type=delivery` و`delivery_area=null`.
- سعر توصيل المنطقة الثابتة يضاف مرة واحدة على الطلب الأب، وليس مرة لكل محل داخل multi-market.
- المندوبون للطلب العام: أي مندوب نشط لديه courier profile. طلب المدينة: المطابقة حسب `Order.service_city` فقط.

## قيم ثابتة مهمة

| الحقل | القيم |
|---|---|
| `role` | `client`, `admin`, `representative` |
| `market_region.mode` | `general`, `service_city`, أو `null` لمسح الاختيار |
| `market.scope` / `offer.scope` / `order_scope` | `general`, `service_city` |
| `delivery_type` | `delivery`, `fixed_area` |
| `order.status` | `pending`, `confirmed`, `assigned`, `picked_up`, `delivered`, `failed_delivery`, `cancelled` |
| `review_status` | `pending_review`, `approved`, `rejected` |
| `offer.type` | `package`, `flash`, `discount`, `announcement`, `delivery` |
| `offer.status` | `active`, `inactive`, `expired` |

## رسائل رفض Scope كما هي

استخدم هذه الرسائل كما هي في عرض الأخطاء:

```text
لا يمكن دمج محلات عامة مع محلات مدينة في نفس الطلب
لا يمكن استخدام عرض مدينة داخل طلب عام
لا يمكن استخدام عرض عام داخل طلب مدينة
لا يمكن دمج منتجات من مدن مختلفة في نفس الطلب
```

## فهرس Endpoints

### Auth

| Method | Path | Auth | ملاحظات |
|---|---|---|---|
| POST | `/api/v1/auth/signup/` | عام | تسجيل وإرسال OTP |
| POST | `/api/v1/auth/verify-email/` | عام | تفعيل التسجيل بالـ OTP |
| POST | `/api/v1/auth/resend-verification/` | عام | إعادة إرسال OTP |
| POST | `/api/v1/auth/login/` | عام | تسجيل دخول عام |
| POST | `/api/v1/auth/login/client/` | عام | دخول عميل فقط |
| POST | `/api/v1/auth/login/representative/` | عام | دخول مندوب فقط |
| POST | `/api/v1/auth/login/admin/` | عام | دخول إدارة فقط |
| POST | `/api/v1/auth/refresh/` | عام | تحديث access token |
| POST | `/api/v1/auth/logout/` | مستخدم | خروج |
| GET/PATCH | `/api/v1/auth/me/` | مستخدم | بيانات المستخدم الحالي |
| GET/PATCH | `/api/v1/auth/client/profile/` | Client | ملف العميل |
| GET/POST | `/api/v1/auth/users/` | Admin | إدارة المستخدمين |
| GET/PATCH/DELETE | `/api/v1/auth/users/{user_id}/` | Admin | مستخدم محدد |
| GET | `/api/v1/auth/representatives/` | Admin | المندوبون |
| GET | `/api/v1/auth/check-username/` | عام | فحص username |
| GET | `/api/v1/auth/check-email/` | عام | فحص email |
| GET | `/api/v1/auth/check-phone/` | عام | فحص phone |
| POST | `/api/v1/auth/forgot-password/` | عام | طلب إعادة كلمة المرور |
| POST | `/api/v1/auth/reset-password/` | عام | إعادة كلمة المرور |

مسارات auth تعمل مع slash وبدون slash.

### Market Region

| Method | Path | Auth | ملاحظات |
|---|---|---|---|
| GET | `/api/v1/market-region/options/` | مستخدم | الخيارات المتاحة مع الاختيار الحالي |
| GET/PATCH | `/api/v1/market-region/me/` | مستخدم | قراءة/تعديل اختيار السوق |
| POST | `/api/v1/market-region/detect/` | مستخدم | اقتراح مدينة حسب latitude/longitude |

### Locations / Addresses

| Method | Path | Auth | ملاحظات |
|---|---|---|---|
| GET/POST | `/api/v1/locations/service-cities/` | Admin | مدن الخدمة |
| GET/PATCH/DELETE | `/api/v1/locations/service-cities/{city_id}/` | Admin | مدينة خدمة |
| GET/POST | `/api/v1/locations/delivery-areas/` | مستخدم حسب الصلاحية | مناطق التوصيل |
| GET/PATCH/DELETE | `/api/v1/locations/delivery-areas/{area_id}/` | مستخدم حسب الصلاحية | منطقة توصيل |
| GET/POST | `/api/v1/locations/addresses/` | مستخدم | عناوين المستخدم، Admin يرسل `user_id` |
| GET | `/api/v1/locations/addresses/default/` | مستخدم | العنوان الافتراضي |
| GET/PATCH/DELETE | `/api/v1/locations/addresses/{address_id}/` | مستخدم | عنوان محدد |
| POST | `/api/v1/locations/addresses/{address_id}/default/` | مستخدم | جعل العنوان افتراضياً |
| GET/POST | `/api/v1/addresses/` | مستخدم | alias لنفس عناوين locations |

### Home / Markets / Catalog / Offers

| Method | Path | Auth | ملاحظات |
|---|---|---|---|
| GET | `/api/v1/home/` | مستخدم | Home حسب `market_region` |
| GET | `/api/v1/home/search/` | مستخدم | بحث منتجات |
| GET | `/api/v1/home/products/` | Client | منتجات حسب عنوان/منطقة العميل، paginated |
| GET | `/api/v1/home/products/{product_id}/` | مستخدم | تفاصيل منتج للعرض |
| GET | `/api/v1/home/classifications/` | مستخدم | تصنيفات وأسواق حسب المنطقة |
| GET | `/api/v1/home/classifications/featured/` | مستخدم | featured فقط |
| GET | `/api/v1/home/classifications/popular/` | مستخدم | popular فقط |
| GET | `/api/v1/home/classifications/normal/` | مستخدم | normal فقط |
| GET | `/api/v1/home/classifications/{classification_id}/markets/` | مستخدم | أسواق تصنيف |
| GET/POST | `/api/v1/home/market-classifications/` | Admin | إدارة تصنيفات المحلات |
| GET/PATCH/DELETE | `/api/v1/home/market-classifications/{classification_id}/` | Admin | تصنيف محل |
| GET/POST | `/api/v1/home/markets/` | Admin | إدارة المحلات |
| GET/PATCH/DELETE | `/api/v1/home/markets/{market_id}/` | Admin | محل محدد |
| GET/POST | `/api/v1/offers/` | مستخدم | Admin يرى الكل وينشئ، Client يرى المتاح حسب المنطقة |
| GET/PATCH/DELETE | `/api/v1/offers/{offer_id}/` | مستخدم | Admin يدير، Client يقرأ المتاح فقط |
| GET/POST | `/api/v1/catalog/products/` | Admin | إدارة المنتجات |
| GET/PATCH/DELETE | `/api/v1/catalog/products/{product_id}/` | Admin | منتج محدد |
| GET | `/api/v1/catalog/products/likes/` | Client | المنتجات المعجب بها |
| POST | `/api/v1/catalog/products/{product_id}/like/` | Client | إعجاب |
| DELETE | `/api/v1/catalog/products/{product_id}/unlike/` | Client | إلغاء إعجاب |

باقي مسارات `/api/v1/catalog/` الإدارية: `addition-classifications`, `category-classifications`, `product-categories`, `category-attributes`, `category-options`, `product-additions` بنفس نمط `GET/POST` للقائمة و`GET/PATCH/DELETE` للتفاصيل.

### Orders

| Method | Path | Auth | ملاحظات |
|---|---|---|---|
| GET | `/api/v1/orders/my/` | Client | طلبات العميل، يدعم `?status=` |
| POST | `/api/v1/orders/preview/` | Client | معاينة السعر والتجميع قبل الإنشاء |
| POST | `/api/v1/orders/create/` | Client | إنشاء طلب، يرجع `[order]` |
| GET/POST | `/api/v1/orders/` | Admin | قائمة/إنشاء إداري |
| GET/PATCH/DELETE | `/api/v1/orders/{order_id}/` | Admin | تفاصيل/تعديل/إلغاء |
| PATCH | `/api/v1/orders/{order_id}/status/` | Admin | تحديث الحالة |
| PATCH | `/api/v1/orders/{order_id}/assignment/` | Admin | إسناد مندوب |
| GET | `/api/v1/admin/order-review/blocker/` | Admin | هل يوجد طلبات مراجعة عالقة |
| POST | `/api/v1/admin/orders/{order_id}/approve/` | Admin | اعتماد الطلب وإرجاع المندوبين المتاحين |
| POST | `/api/v1/admin/orders/{order_id}/reject/` | Admin | رفض الطلب |
| GET | `/api/v1/admin/orders/{order_id}/service-city-representatives/` | Admin | مندوبون مؤهلون للطلب |

### Courier / Notifications / Dashboard

| Method | Path | Auth | ملاحظات |
|---|---|---|---|
| GET | `/api/v1/courier/orders/` | Courier | طلبات المندوب، يدعم `?status=` |
| GET | `/api/v1/courier/orders/{order_id}/` | Courier | تفاصيل طلب مسند للمندوب |
| PATCH | `/api/v1/courier/orders/{order_id}/status/` | Courier | انتقال الحالة |
| GET | `/api/v1/notifications/` | مستخدم | إشعارات المستخدم، فلاتر: `unread`, `type`, `audience`, `is_blocking`, `is_resolved` |
| PATCH | `/api/v1/notifications/{notification_id}/read/` | مستخدم | تعليم إشعار كمقروء |
| POST | `/api/v1/notifications/mark-all-read/` | مستخدم | تعليم الكل كمقروء |
| GET | `/api/v1/notifications/unread-count/` | مستخدم | عدد غير المقروء |
| GET | `/api/v1/dashboard/overview/?from=YYYY-MM-DD&to=YYYY-MM-DD` | Admin | ملخص لوحة التحكم |

## Auth Examples

### Admin login

Request:

```json
{
  "email": "seed.admin@yalla.seed",
  "password": "SeedPass1!"
}
```

Response `200`:

```json
{
  "accessToken": "<accessToken>",
  "refreshToken": "<refreshToken>",
  "expiresIn": 900,
  "user": {
    "id": "1",
    "first_name": "مدير",
    "last_name": "يلا",
    "username": "seed_admin",
    "email": "seed.admin@yalla.seed",
    "phone": "+201001000001",
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

المسار الفعلي هو `POST /api/v1/auth/login/client/` ويعمل أيضاً بدون slash أخير. يقبل `identifier` كبريد أو username أو هاتف، ويقبل `email` للتوافق. اسم حقل الاختيار هو `remember`؛ القيمة المفقودة تُعامل كـ `false`.

Request مؤقت:

```json
{
  "identifier": "<test-identifier>",
  "password": "<redacted>",
  "remember": false
}
```

Response `200` الفعلي بعد تنقيح الأسرار والهوية:

```json
{
  "accessToken": "<redacted>",
  "refreshToken": "<redacted>",
  "expiresIn": 900,
  "session": {
    "mode": "temporary",
    "remember": false,
    "startedAt": "2026-07-13T10:08:25Z",
    "absoluteExpiresAt": "2026-07-13T18:08:25Z",
    "accessExpiresAt": "2026-07-13T10:23:25Z",
    "refreshExpiresAt": "2026-07-13T18:08:25Z"
  },
  "user": {
    "id": "<redacted>",
    "email": "<redacted>",
    "role": "client",
    "is_active": true
  }
}
```

Request دائم:

```json
{
  "identifier": "<test-identifier>",
  "password": "<redacted>",
  "remember": true
}
```

Response `200` الفعلي المنقح:

```json
{
  "accessToken": "<redacted>",
  "refreshToken": "<redacted>",
  "expiresIn": 900,
  "session": {
    "mode": "persistent",
    "remember": true,
    "startedAt": "2026-07-13T10:08:26Z",
    "absoluteExpiresAt": null,
    "accessExpiresAt": "2026-07-13T10:23:26Z",
    "refreshExpiresAt": "2026-07-20T10:08:26Z"
  },
  "user": {
    "id": "<redacted>",
    "email": "<redacted>",
    "role": "client",
    "is_active": true
  }
}
```

### Mobile app session contract

- الـ access token قصير العمر: 15 دقيقة كحد أقصى.
- `remember=false` أو غياب الحقل ينشئ جلسة مؤقتة بموعد نهائي مطلق بعد 8 ساعات من `startedAt`.
- كل refresh للجلسة المؤقتة يحافظ على نفس `startedAt` و`absoluteExpiresAt`؛ لا يمدد الثماني ساعات. عند قرب الموعد النهائي تُقصّر صلاحية access كي لا تتجاوزه.
- `remember=true` ينشئ جلسة دائمة بنافذة خمول 7 أيام. refresh ناجح بسبب استخدام التطبيق يدوّر refresh token ويجعل `refreshExpiresAt` الجديد بعد 7 أيام من لحظة التحديث.
- refresh token القديم يدخل blacklist فور التدوير ولا يمكن إعادة استخدامه.
- لا يوجد refresh خلفي دوري لإبقاء تطبيق غير مستخدم مسجلاً.
- السياسة تطبق على دخول `client` و`representative` من تطبيقات الهاتف. سلوك admin بقي منفصلاً كما كان.
- توكن عميل أو مندوب قديم بلا session claims يعامل مؤقتاً بمهلة 8 ساعات من `iat` لأن اختيار الجلسة الأصلي لا يمكن استعادته بأمان.

Refresh request الفعلي:

```http
POST /api/v1/auth/refresh/
Content-Type: application/json

{"refreshToken":"<redacted>"}
```

Response مؤقت فعلي منقح؛ لاحظ ثبات الموعد المطلق:

```json
{
  "accessToken": "<redacted>",
  "refreshToken": "<redacted>",
  "expiresIn": 900,
  "session": {
    "mode": "temporary",
    "remember": false,
    "startedAt": "2026-07-13T10:08:25Z",
    "absoluteExpiresAt": "2026-07-13T18:08:25Z",
    "accessExpiresAt": "2026-07-13T10:23:25Z",
    "refreshExpiresAt": "2026-07-13T18:08:25Z"
  }
}
```

Response دائم فعلي منقح:

```json
{
  "accessToken": "<redacted>",
  "refreshToken": "<redacted>",
  "expiresIn": 900,
  "session": {
    "mode": "persistent",
    "remember": true,
    "startedAt": "2026-07-13T10:08:26Z",
    "absoluteExpiresAt": null,
    "accessExpiresAt": "2026-07-13T10:23:26Z",
    "refreshExpiresAt": "2026-07-20T10:08:26Z"
  }
}
```

إعادة استخدام refresh قديم بعد rotation أو logout ترجع فعلياً `401`:

```json
{
  "detail": "Token is blacklisted",
  "code": "token_not_valid"
}
```

الجلسة التي تجاوزت نافذة الخمول/الموعد المطلق ترجع `401` بالشكل المثبت في اختبارات الوقت المتحكم فيه:

```json
{
  "code": "session_expired",
  "detail": "Session expired. Please login again."
}
```

الحساب غير النشط له الأولوية حتى لو كان refresh token قديماً ومدرجاً في blacklist. طلب `curl` الفعلي رجع `403`:

```json
{
  "code": "account_inactive",
  "detail": "تم إيقاف حسابك. تواصل مع الدعم."
}
```

`GET /api/v1/auth/me/` يرجع كائن المستخدم مباشرة، وليس داخل مفتاح `user`. مثال منقح:

```json
{
  "id": "<redacted>",
  "email": "<redacted>",
  "first_name": "<redacted>",
  "last_name": "<redacted>",
  "role": "client",
  "is_active": true
}
```

Logout request الفعلي:

```http
POST /api/v1/auth/logout/
Authorization: Bearer <redacted>
Content-Type: application/json

{"refreshToken":"<redacted>"}
```

Response `200`:

```json
{"detail":"Logout successful."}
```

الـ logout يضع refresh الحالي في blacklist. access المنسوخ قبل logout يبقى صالحاً حتى انتهاء حدّه القصير (15 دقيقة كحد أقصى)، وهو سلوك JWT الحالي المقصود؛ تطبيق Flutter يمسحه محلياً فوراً.

### Flutter session handling

- Android وiOS: الجلسة الدائمة فقط تُكتب في `flutter_secure_storage`. الجلسة المؤقتة تبقى في الذاكرة، لذلك موت process ينهيها.
- Web: الجلسة المؤقتة تستخدم `window.sessionStorage`، لا persistent local storage؛ إغلاق tab/window ينهيها. الجلسة الدائمة تستخدم مخزن التوكن الآمن الدائم الحالي.
- كلمة المرور وcheckbox لا يتم تخزينهما.
- عند startup تستعاد الجلسة الدائمة، يُفحص deadline، يحدث access عند الحاجة، ثم يُتحقق من المستخدم عبر `/auth/me/`. الجلسة المؤقتة لا تستعاد بعد mobile process restart.
- قبل كل طلب محمي يفحص العميل انتهاء access بهامش دقيقة. كما يعالج `401` الحقيقي، يحدّث مرة، ثم يعيد الطلب الأصلي مرة واحدة فقط.
- refresh متزامن single-flight: الطلبات المتوازية تنتظر نفس العملية، ثم تستخدم نفس access الجديد. حفظ access وrefresh المدورين يتم بعملية store واحدة.
- عند resume لا يحدث refresh إلا بسبب استخدام foreground؛ يفحص deadline ثم يستدعي مسار التحقق الحالي من الحساب.
- عند deadline المؤقت يمسح التوكنات والحالة الخاصة، يمسح protected navigation stack، ويعرض رسالة انتهاء الجلسة العربية.
- logout يحاول إلغاء جهاز FCM والـ backend refresh، لكنه يكمل المسح المحلي والتنقل للدخول حتى عند فشل الشبكة.

### Sanitized curl commands used on 2026-07-13

القيم أتت من متغيرات shell مؤقتة؛ لم تُكتب credentials أو JWTs في المصدر أو هذا التقرير:

```bash
curl -sS -X POST "$BASE_URL/api/v1/auth/login/client/" \
  -H 'Content-Type: application/json' \
  --data '{"identifier":"<redacted>","password":"<redacted>"}'

curl -sS -X POST "$BASE_URL/api/v1/auth/login/client/" \
  -H 'Content-Type: application/json' \
  --data '{"identifier":"<redacted>","password":"<redacted>","remember":false}'

curl -sS -X POST "$BASE_URL/api/v1/auth/login/client/" \
  -H 'Content-Type: application/json' \
  --data '{"identifier":"<redacted>","password":"<redacted>","remember":true}'

curl -sS -X POST "$BASE_URL/api/v1/auth/refresh/" \
  -H 'Content-Type: application/json' \
  --data '{"refreshToken":"<redacted>"}'

curl -sS "$BASE_URL/api/v1/auth/me/" \
  -H 'Authorization: Bearer <redacted>'

curl -sS -X POST "$BASE_URL/api/v1/auth/logout/" \
  -H 'Authorization: Bearer <redacted>' \
  -H 'Content-Type: application/json' \
  --data '{"refreshToken":"<redacted>"}'

curl -sS -X POST "$BASE_URL/api/v1/auth/login/representative/" \
  -H 'Content-Type: application/json' \
  --data '{"identifier":"<redacted>","password":"<redacted>","remember":true}'
```

### Courier login

المسار الفعلي هو `POST /api/v1/auth/login/representative/`. يقبل نفس `identifier` وحقل `remember`، والقيمة المفقودة آمنة وتساوي `false`.

التحقق الفعلي المنقح في 2026-07-13 أعاد للجلسة الدائمة:

```json
{
  "accessToken": "<redacted>",
  "refreshToken": "<redacted>",
  "expiresIn": 900,
  "session": {
    "mode": "persistent",
    "remember": true,
    "startedAt": "2026-07-13T11:06:20Z",
    "absoluteExpiresAt": null,
    "accessExpiresAt": "2026-07-13T11:21:20Z",
    "refreshExpiresAt": "2026-07-20T11:06:20Z"
  },
  "user": {
    "id": "<redacted>",
    "email": "<redacted>",
    "role": "representative",
    "is_active": true
  }
}
```

غياب `remember` و`remember=false` أعادا فعلياً `mode=temporary` مع `absoluteExpiresAt` بعد 8 ساعات. تدوير refresh غيّر access وrefresh معاً، وحافظ على الموعد المطلق للمؤقت. إعادة استخدام القديم أو refresh بعد logout أعادت `401 token_not_valid`.

Response الكامل يحتوي أيضاً `courier_profile` لأن الدور `representative`:

```json
{
  "accessToken": "<accessToken>",
  "refreshToken": "<refreshToken>",
  "expiresIn": 900,
  "user": {
    "id": "5",
    "first_name": "أحمد",
    "last_name": "مندوب",
    "username": "seed_courier1",
    "email": "seed.courier1@yalla.seed",
    "phone": "+201001000004",
    "gender": "",
    "birth_date": null,
    "avatar_url": null,
    "username_changed_at": null,
    "role": "representative",
    "has_password": true,
    "courier_profile": {
      "vehicle_type": "دراجة نارية",
      "plate_number": "س ي د 1234",
      "delivery_area": 1,
      "delivery_area_name": "مدينة نصر",
      "service_city": 1,
      "service_city_name": "القاهرة",
      "max_active_orders": 4,
      "is_available": true
    }
  }
}
```

### Signup

Request:

```json
{
  "first_name": "Report",
  "last_name": "User",
  "username": "report_user",
  "email": "report.user@yalla.test",
  "phone": "+201009999999",
  "password": "StrongPass1!",
  "password_confirm": "StrongPass1!"
}
```

Response `201`:

```json
{
  "detail": "Registration OTP sent.",
  "email": "report.user@yalla.test",
  "dev_otp": "<dev_otp>"
}
```

في بيئة التطوير قد يظهر `dev_otp`. في الإنتاج لا تعتمد عليه كقيمة ثابتة.

## Market Region

اختيار المنطقة هو فلتر السوق والطلبات. بدون اختيار قد ترجع endpoints العميل خطأ مثل:

```json
{
  "detail": "Select a market browsing region before loading market content.",
  "requires_market_region_selection": true
}
```

تغيير الاختيار:

```http
PATCH /api/v1/market-region/me/
```

General:

```json
{
  "mode": "general",
  "service_city_id": null
}
```

Service city:

```json
{
  "mode": "service_city",
  "service_city_id": 1
}
```

مسح الاختيار:

```json
{
  "mode": null,
  "service_city_id": null
}
```

Response example:

```json
{
  "current_selection": {
    "mode": "service_city",
    "label": "القاهرة",
    "service_city": {
      "id": 1,
      "name": "القاهرة",
      "delivery_price": 45.0,
      "is_active": true
    },
    "updated_at": "2026-07-05T15:42:34.729502Z"
  }
}
```

## Locations And Addresses

### Service city example

```json
{
  "id": 3,
  "name": "الإسكندرية",
  "center_latitude": "31.2001000",
  "center_longitude": "29.9187000",
  "radius_km": "24.00",
  "delivery_price": "55.00",
  "is_active": true
}
```

### Delivery area example

```json
{
  "id": 5,
  "service_city_id": 2,
  "name": "الدقي",
  "center_latitude": "30.0384000",
  "center_longitude": "31.2123000",
  "radius_km": "6.50",
  "delivery_price": "50.00",
  "is_active": true
}
```

### General manual address

يستخدم فقط عندما اختيار المستخدم `market_region.mode=general`:

```http
POST /api/v1/locations/addresses/
```

Request:

```json
{
  "name": "عنوان عام",
  "line1": "شارع الثورة بجوار بنزينة التعاون",
  "manual_city": "القاهرة",
  "manual_area": "مصر الجديدة",
  "service_city_id": null,
  "delivery_area_id": null,
  "latitude": "30.0860000",
  "longitude": "31.3300000",
  "isDefault": true
}
```

Response shape:

```json
{
  "id": 4,
  "name": "عنوان عام",
  "fullName": "عنوان عام",
  "phone": "+201001000003",
  "phoneNumber": "+201001000003",
  "line1": "شارع الثورة بجوار بنزينة التعاون",
  "street": "شارع الثورة بجوار بنزينة التعاون",
  "city": "",
  "state": "",
  "country": "Egypt",
  "postalCode": "",
  "latitude": "30.0860000",
  "longitude": "31.3300000",
  "details": "شارع الثورة بجوار بنزينة التعاون",
  "manual_city": "القاهرة",
  "manual_area": "مصر الجديدة",
  "service_city": null,
  "service_city_id": null,
  "service_city_name": null,
  "delivery_area": null,
  "delivery_area_id": null,
  "delivery_area_name": null,
  "delivery_area_price": null,
  "delivery_type": "delivery",
  "delivery_price_preview": null,
  "is_default": true,
  "isDefault": true,
  "created_at": "2026-07-05T15:42:38.609944Z"
}
```

### Service-city fixed-area address

Request:

```json
{
  "name": "عنوان السلام",
  "line1": "السلام، شارع رئيسي",
  "service_city_id": 1,
  "delivery_area_id": 4,
  "manual_city": null,
  "manual_area": null,
  "isDefault": false
}
```

النظام يجعل `delivery_type=fixed_area` ويعرض `delivery_price_preview` من سعر `delivery_area`.

### Service-city unsupported/manual area address

Request:

```json
{
  "name": "عنوان آخر",
  "line1": "القاهرة، منطقة غير مضافة، قرب الطريق الرئيسي",
  "service_city_id": 1,
  "delivery_area_id": null,
  "manual_city": null,
  "manual_area": "منطقة غير مضافة",
  "latitude": "30.0130000",
  "longitude": "31.4280000"
}
```

النظام يجعل `delivery_type=delivery`, `delivery_area=null`, `delivery_price_preview=null`.

## Catalog / Home / Offers

- Admin endpoints تحت `/api/v1/catalog/` و`/api/v1/home/markets/` ترجع بيانات إدارية كاملة.
- Client home/offers/search ترجع فقط المحلات والمنتجات والعروض المطابقة لاختيار `market_region`.
- Product variants هي التي تُرسل في الطلبات عبر `variant_id`، وليس `product_id`.

Product example:

```json
{
  "id": 6,
  "market": {
    "id": 1,
    "name": "سوق يلا العام",
    "branch": "",
    "status": "active",
    "classification_id": 1
  },
  "category": {
    "id": 3,
    "name": "منتجات بقالة",
    "classification": {
      "id": 2,
      "name": "منتجات غذائية"
    }
  },
  "is_available": true,
  "name": "أرز مصري",
  "description": "أرز أبيض درجة أولى.",
  "image": null,
  "discount": "0.00",
  "variants": [
    {
      "id": 11,
      "price": "55.00",
      "sku": "SEED-0006-1",
      "attribute_values": [
        {
          "id": 7,
          "attribute": {
            "id": 8,
            "name": "العبوة",
            "options": [
              {
                "id": 20,
                "value": "عبوة"
              },
              {
                "id": 21,
                "value": "كرتونة"
              }
            ]
          },
          "option": {
            "id": 20,
            "value": "عبوة"
          }
        }
      ]
    },
    {
      "id": 12,
      "price": "105.00",
      "sku": "SEED-0006-2",
      "attribute_values": [
        {
          "id": 8,
          "attribute": {
            "id": 8,
            "name": "العبوة",
            "options": [
              {
                "id": 20,
                "value": "عبوة"
              },
              {
                "id": 21,
                "value": "كرتونة"
              }
            ]
          },
          "option": {
            "id": 21,
            "value": "كرتونة"
          }
        }
      ]
    }
  ],
  "additions": [
    5
  ],
  "created_at": "2026-07-05T15:42:38.649818Z",
  "updated_at": "2026-07-05T15:42:38.649835Z"
}
```

Offer example:

```json
{
  "id": 18,
  "market_id": 5,
  "scope": "service_city",
  "service_city_id": 3,
  "service_city": {
    "id": 3,
    "name": "الإسكندرية",
    "delivery_price": "55.00",
    "is_active": true
  },
  "product_ids": [
    31
  ],
  "title": "عرض مخبز منتهي",
  "description": "عرض مخبز منتهي متاح ضمن بيانات العرض التجريبية.",
  "image": null,
  "type": "discount",
  "discount": "15.00",
  "start_time": "2026-06-15T15:42:34.729502Z",
  "end_time": "2026-07-04T15:42:34.729502Z",
  "active_days": [
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday"
  ],
  "use_limits": null,
  "user_limit": null,
  "status": "expired"
}
```

## Orders Client Flow

الخطوات الموصى بها للعميل:

1. Login.
2. اختيار `/api/v1/market-region/me/`.
3. إنشاء/اختيار address متوافق مع نفس المنطقة.
4. استدعاء `/api/v1/orders/preview/`.
5. إن كان preview مناسباً، استدعاء `/api/v1/orders/create/` بنفس `items/offers/address_id` مع `payment_method`.

### Preview request shape

```json
{
  "address_id": 4,
  "items": [
    {"variant_id": 5, "quantity": 2}
  ],
  "offers": [
    {"offer_id": 1}
  ]
}
```

`items` أو `offers` واحد منهم على الأقل مطلوب.

### Create request shape

```json
{
  "address_id": 4,
  "items": [
    {"variant_id": 5, "quantity": 2}
  ],
  "offers": [
    {"offer_id": 1}
  ],
  "payment_method": "cash",
  "description": "",
  "delivery_note": ""
}
```

## General Multi-Market Order

هذا المثال يثبت السلوك الصحيح لطلب عام بعنوان يدوي في القاهرة/مصر الجديدة: النص محفوظ، لكن الطلب يبقى `general` ولا يأخذ `service_city`.

Preview request:

```json
{
  "address_id": 4,
  "items": [
    {"variant_id": 5, "quantity": 2},
    {"variant_id": 13, "quantity": 1}
  ],
  "offers": [
    {"offer_id": 1}
  ]
}
```

Preview response `200`:

```json
{
  "order_scope": "general",
  "service_city": null,
  "selected_address": {
    "id": 4,
    "name": "عنوان عام",
    "manual_city": "القاهرة",
    "manual_area": "مصر الجديدة",
    "service_city": null,
    "service_city_id": null,
    "delivery_area": null,
    "delivery_area_id": null,
    "delivery_type": "delivery",
    "delivery_price_preview": null,
    "is_default": true
  },
  "market_count": 2,
  "is_multi_market": true,
  "market_names_summary": "سوق يلا العام, متجر العروض العامة",
  "market_groups": [
    {
      "market": {
        "id": 1,
        "name": "سوق يلا العام",
        "branch": ""
      },
      "service_city": null,
      "delivery_area": null,
      "delivery_type": "delivery",
      "delivery_price": null,
      "delivery_message": "Delivery price will be determined later.",
      "delivery_available": true,
      "selected_products": [
        {
          "variant_id": 5,
          "product_id": 3,
          "product_name": "مياه معدنية",
          "image": null,
          "quantity": 2,
          "unit_price": "35.00",
          "subtotal": "70.00"
        }
      ],
      "selected_offers": [
        {
          "id": 1,
          "title": "عرض الجمعة العام",
          "type": "flash",
          "discount_percentage": "15.00",
          "discount_amount": "51.00",
          "products_count": 3
        }
      ],
      "pricing": {
        "products_subtotal": "340.00",
        "total_offer_discounts": "51.00",
        "delivery_price": null,
        "market_total": "289.00"
      }
    },
    {
      "market": {
        "id": 2,
        "name": "متجر العروض العامة",
        "branch": ""
      },
      "service_city": null,
      "delivery_area": null,
      "delivery_type": "delivery",
      "delivery_price": null,
      "delivery_message": "Delivery price will be determined later.",
      "delivery_available": true,
      "selected_products": [
        {
          "variant_id": 13,
          "product_id": 7,
          "product_name": "كرتونة رمضان",
          "image": null,
          "quantity": 1,
          "unit_price": "700.00",
          "subtotal": "700.00"
        }
      ],
      "selected_offers": [],
      "pricing": {
        "products_subtotal": "700.00",
        "total_offer_discounts": "0.00",
        "delivery_price": null,
        "market_total": "700.00"
      }
    }
  ],
  "summary": {
    "subtotal": "1040.00",
    "discount_total": "51.00",
    "delivery_total": "0.00",
    "grand_total": "989.00"
  }
}
```

Create response `201`: لاحظ أنها قائمة بعنصر واحد.

```json
[
  {
    "id": 26,
    "customer": {
      "id": 3,
      "name": "كريم محمود",
      "phone": "+201001000003"
    },
    "order_scope": "general",
    "service_city_id": null,
    "service_city": null,
    "delivery_area_id": null,
    "delivery_area": null,
    "delivery_type": "delivery",
    "delivery_price": null,
    "payment_method": "cash",
    "status": "pending",
    "review_status": "pending_review",
    "subtotal_price": "1040.00",
    "discount": "51.00",
    "total_price": "989.00",
    "delivery_address": {
      "id": 4,
      "name": "عنوان عام",
      "details": "شارع الثورة بجوار بنزينة التعاون",
      "manual_city": "القاهرة",
      "manual_area": "مصر الجديدة",
      "service_city": null,
      "delivery_area": null,
      "delivery_type": "delivery",
      "delivery_price_preview": null
    },
    "is_multi_market": true,
    "market_count": 2,
    "market_names_summary": "سوق يلا العام, متجر العروض العامة",
    "market_sections": [
      {
        "id": 29,
        "market_id": 1,
        "market": {
          "id": 1,
          "name": "سوق يلا العام",
          "branch": "",
          "status": "active"
        },
        "subtotal_price": "340.00",
        "discount": "51.00",
        "total_price": "289.00",
        "pickup_status": "pending",
        "sort_order": 0,
        "items": [
          {
            "id": 45,
            "section_id": 29,
            "variant_id": 5,
            "quantity": 2,
            "unit_price": "35.00"
          },
          {
            "id": 46,
            "section_id": 29,
            "variant_id": 7,
            "quantity": 1,
            "unit_price": "120.00"
          },
          {
            "id": 47,
            "section_id": 29,
            "variant_id": 9,
            "quantity": 1,
            "unit_price": "150.00"
          }
        ],
        "offers": [
          {
            "id": 15,
            "section_id": 29,
            "offer_id": 1,
            "discount_amount": "51.00",
            "created_at": "2026-07-05T15:42:43.514327Z"
          }
        ]
      },
      {
        "id": 30,
        "market_id": 2,
        "market": {
          "id": 2,
          "name": "متجر العروض العامة",
          "branch": "",
          "status": "active"
        },
        "subtotal_price": "700.00",
        "discount": "0.00",
        "total_price": "700.00",
        "pickup_status": "pending",
        "sort_order": 1,
        "items": [
          {
            "id": 48,
            "section_id": 30,
            "variant_id": 13,
            "quantity": 1,
            "unit_price": "700.00"
          }
        ],
        "offers": []
      }
    ],
    "pickup_stops": [
      {
        "market_id": 1,
        "market": {
          "id": 1,
          "name": "سوق يلا العام",
          "branch": "",
          "status": "active"
        },
        "pickup_status": "pending",
        "picked_up_at": null,
        "sort_order": 0
      },
      {
        "market_id": 2,
        "market": {
          "id": 2,
          "name": "متجر العروض العامة",
          "branch": "",
          "status": "active"
        },
        "pickup_status": "pending",
        "picked_up_at": null,
        "sort_order": 1
      }
    ]
  }
]
```

الحقول المهمة في الربط:

- `order_scope="general"`
- `service_city_id=null`
- `delivery_area_id=null`
- `delivery_type="delivery"`
- `delivery_price=null`
- `market_sections` يحتوي كل محل داخل الطلب الأب.
- `pickup_stops` يستخدم لتتبع استلام المندوب من كل محل.
- `items` و`offers` ما زالت موجودة كتوافق قديم، لكن الربط الجديد الأفضل يعتمد على `market_sections` أو `grouped_items/grouped_offers`.

## Service-City Fixed-Area Order

Preview request:

```json
{
  "address_id": 3,
  "items": [
    {"variant_id": 25, "quantity": 1}
  ],
  "offers": [
    {"offer_id": 4}
  ]
}
```

Preview response:

```json
{
  "order_scope": "service_city",
  "service_city": {
    "id": 1,
    "name": "القاهرة",
    "delivery_price": "45.00",
    "is_active": true
  },
  "selected_address": {
    "id": 3,
    "name": "عنوان السلام",
    "manual_city": null,
    "manual_area": null,
    "service_city": {
      "id": 1,
      "name": "القاهرة",
      "delivery_price": "45.00",
      "is_active": true
    },
    "service_city_id": 1,
    "delivery_area": {
      "id": 4,
      "service_city_id": 1,
      "name": "السلام",
      "delivery_price": "46.00",
      "is_active": true
    },
    "delivery_area_id": 4,
    "delivery_type": "fixed_area",
    "delivery_price_preview": "46.00",
    "is_default": false
  },
  "market_count": 1,
  "is_multi_market": false,
  "market_names_summary": "مطبخ النيل العائلي",
  "market_groups": [
    {
      "market": {
        "id": 3,
        "name": "مطبخ النيل العائلي",
        "branch": "مدينة نصر"
      },
      "service_city": {
        "id": 1,
        "name": "القاهرة",
        "delivery_price": "45.00",
        "is_active": true
      },
      "delivery_area": {
        "id": 4,
        "service_city_id": 1,
        "name": "السلام",
        "delivery_price": "46.00",
        "is_active": true
      },
      "delivery_type": "fixed_area",
      "delivery_price": "46.00",
      "delivery_message": "",
      "delivery_available": true,
      "selected_products": [
        {
          "variant_id": 25,
          "product_id": 13,
          "product_name": "دجاج مشوي",
          "image": null,
          "quantity": 1,
          "unit_price": "180.00",
          "subtotal": "180.00"
        }
      ],
      "selected_offers": [
        {
          "id": 4,
          "title": "باقة العائلة",
          "type": "package",
          "discount_percentage": "18.00",
          "discount_amount": "69.30",
          "products_count": 3
        }
      ],
      "pricing": {
        "products_subtotal": "385.00",
        "total_offer_discounts": "69.30",
        "delivery_price": "46.00",
        "market_total": "361.70"
      }
    }
  ],
  "summary": {
    "subtotal": "385.00",
    "discount_total": "69.30",
    "delivery_total": "46.00",
    "grand_total": "361.70"
  }
}
```

في هذا المثال العنوان مربوط بمنطقة `السلام` داخل القاهرة، لذلك:

- `order_scope="service_city"`
- `delivery_type="fixed_area"`
- `delivery_area.id=4`
- `delivery_price="46.00"`
- `summary.delivery_total="46.00"` مرة واحدة على الطلب الأب.

## Service-City Unsupported/Manual Area Order

Create request:

```json
{
  "address_id": 2,
  "items": [
    {"variant_id": 25, "quantity": 1}
  ],
  "payment_method": "cash"
}
```

Create response `201`:

```json
[
  {
    "id": 27,
    "customer": {
      "id": 2,
      "name": "أمينة حسن",
      "phone": "+201001000002"
    },
    "order_scope": "service_city",
    "service_city_id": 1,
    "service_city": {
      "id": 1,
      "name": "القاهرة",
      "delivery_price": "45.00",
      "is_active": true
    },
    "delivery_area_id": null,
    "delivery_area": null,
    "delivery_type": "delivery",
    "delivery_price": null,
    "payment_method": "cash",
    "status": "pending",
    "review_status": "pending_review",
    "subtotal_price": "180.00",
    "discount": "0.00",
    "total_price": "180.00",
    "delivery_address": {
      "id": 2,
      "name": "عنوان آخر",
      "details": "القاهرة، منطقة غير مضافة، قرب الطريق الرئيسي",
      "manual_city": null,
      "manual_area": "منطقة غير مضافة",
      "service_city": {
        "id": 1,
        "name": "القاهرة",
        "delivery_price": "45.00",
        "is_active": true
      },
      "delivery_area": null,
      "delivery_type": "delivery",
      "delivery_price_preview": null
    },
    "is_multi_market": false,
    "market_count": 1,
    "market_names_summary": "مطبخ النيل العائلي",
    "market_sections": [
      {
        "id": 31,
        "market_id": 3,
        "market": {
          "id": 3,
          "name": "مطبخ النيل العائلي",
          "branch": "مدينة نصر",
          "status": "active"
        },
        "subtotal_price": "180.00",
        "discount": "0.00",
        "total_price": "180.00",
        "pickup_status": "pending",
        "sort_order": 0,
        "items": [
          {
            "id": 49,
            "section_id": 31,
            "variant_id": 25,
            "quantity": 1,
            "unit_price": "180.00"
          }
        ],
        "offers": []
      }
    ],
    "pickup_stops": [
      {
        "market_id": 3,
        "market": {
          "id": 3,
          "name": "مطبخ النيل العائلي",
          "branch": "مدينة نصر",
          "status": "active"
        },
        "pickup_status": "pending",
        "picked_up_at": null,
        "sort_order": 0
      }
    ]
  }
]
```

هذا هو السلوك المقصود عندما تكون المنطقة غير مضافة في `DeliveryArea`:

- `service_city` تبقى القاهرة.
- `delivery_area=null`.
- `delivery_type="delivery"`.
- `delivery_price=null`.
- `delivery_address.manual_area` يظهر للمندوب والإدارة.
- إسناد المندوب يطابق `Order.service_city` وليس `delivery_area`.

## Order Response Contract

أهم الحقول في `OrderSerializer`:

| الحقل | النوع | ملاحظات |
|---|---|---|
| `id` | number | رقم الطلب |
| `customer` | object | `id`, `name`, `phone` |
| `delivery_address` | object/null | يحتوي `manual_city`, `manual_area`, `delivery_area`, `delivery_type` |
| `assigned_representative_id` | number/null | المندوب المسند |
| `market` | object | أول محل للتوافق القديم |
| `order_scope` | string | `general` أو `service_city` |
| `service_city` | object/null | null في الطلب العام |
| `delivery_area` | object/null | null في العام أو المنطقة اليدوية |
| `delivery_type` | string | `delivery` أو `fixed_area` |
| `delivery_price` | string/null | null عندما السعر يحدد لاحقاً |
| `subtotal_price` | string | مجموع المنتجات قبل الخصم والتوصيل |
| `discount` | string | خصم العروض |
| `total_price` | string | النهائي |
| `review_status` | string | يبدأ `pending_review` |
| `market_sections` | array | المصدر الأساسي لتجميع المحلات |
| `grouped_items` | array | توافق للعرض حسب المحل |
| `grouped_offers` | array | توافق للعروض حسب المحل |
| `pickup_stops` | array | نقاط الاستلام للمندوب |
| `items` | array | توافق قديم، لا يكفي وحده للـ multi-market |
| `offers` | array | توافق قديم |

## Admin Order Flow

### Review blocker

```http
GET /api/v1/admin/order-review/blocker/
```

Response fields:

- `blocked`: boolean، تكون `true` إذا يوجد طلبات `pending_review`.
- `pending_count`: عدد الطلبات التي تنتظر مراجعة الإدارة.
- `orders`: قائمة `OrderSerializer[]` لنفس الطلبات العالقة.

### Approve

```http
POST /api/v1/admin/orders/{order_id}/approve/
```

Response example:

```json
{
  "message": "Order approved successfully.",
  "order": {
    "id": 27,
    "order_scope": "service_city",
    "service_city_id": 1,
    "delivery_area_id": null,
    "delivery_type": "delivery",
    "status": "confirmed",
    "review_status": "approved",
    "assigned_representative_id": null
  },
  "service_city": {
    "id": 1,
    "name": "القاهرة"
  },
  "available_representatives": [
    {
      "representative_id": 5,
      "user_id": 5,
      "name": "أحمد مندوب",
      "phone": "+201001000004",
      "service_city_id": 1,
      "service_city": "القاهرة"
    },
    {
      "representative_id": 6,
      "user_id": 6,
      "name": "محمود مندوب",
      "phone": "+201001000005",
      "service_city_id": 1,
      "service_city": "القاهرة"
    }
  ]
}
```

للطلب العام `service_city` في هذه الاستجابة يكون `null`، و`available_representatives` يرجع أي مندوب نشط لديه `courier_profile`.

### Representatives for order

```http
GET /api/v1/admin/orders/{order_id}/service-city-representatives/
```

- طلب `service_city`: يرجع مندوبين نفس `Order.service_city`.
- طلب `general`: يرجع كل المندوبين النشطين المتاحين أصحاب profile، و`service_city=null`.

### Assign courier

```http
PATCH /api/v1/orders/{order_id}/assignment/
```

Request:

```json
{
  "representative_id": 5
}
```

Response example:

```json
{
  "message": "Order assigned successfully.",
  "order": {
    "id": 27,
    "status": "assigned",
    "review_status": "approved",
    "assigned_representative_id": 5
  },
  "representative": {
    "representative_id": 5,
    "user_id": 5,
    "name": "أحمد مندوب",
    "phone": "+201001000004",
    "service_city_id": 1,
    "service_city": "القاهرة"
  }
}
```

بعد الإسناد يصبح `status="assigned"` ويُملأ `assigned_at`.

### Admin create order

```http
POST /api/v1/orders/
```

Request minimum:

```json
{
  "user_id": 2,
  "delivery_address_id": 2,
  "market_id": 3,
  "payment_method": "cash",
  "description": "",
  "delivery_note": "",
  "items": [
    {"variant_id": 25, "quantity": 1, "unit_price": "0.00"}
  ],
  "offers": []
}
```

ملاحظة مهمة: عند الإنشاء الإداري لا ترسل الحقول التالية لأنها system-controlled وسيتم رفضها لو كانت موجودة: `order_scope`, `delivery_area_id`, `delivery_type`, `delivery_price`, `discount`, `subtotal_price`, `total_price`, `status`, `review_status`, `assigned_representative_id`, `assigned_at`, `delivered_at`, `approved_by`, `approved_at`, `rejected_by`, `rejected_at`, `rejection_reason`, `image`, `delivery_proof`.

## Courier Flow

### List assigned orders

```http
GET /api/v1/courier/orders/
```

Response example:

```json
[
  {
    "id": 27,
    "status": "assigned",
    "order_scope": "service_city",
    "service_city": {
      "id": 1,
      "name": "القاهرة",
      "delivery_price": "45.00",
      "is_active": true
    },
    "delivery_area": null,
    "delivery_type": "delivery",
    "market": {
      "id": 3,
      "name": "مطبخ النيل العائلي",
      "branch": "مدينة نصر",
      "status": "active"
    },
    "market_count": 1,
    "customer": {
      "id": 2,
      "name": "أمينة حسن",
      "phone": "+201001000002"
    },
    "delivery_address": {
      "id": 2,
      "name": "عنوان آخر",
      "details": "القاهرة، منطقة غير مضافة، قرب الطريق الرئيسي",
      "manual_city": null,
      "manual_area": "منطقة غير مضافة",
      "delivery_area": null,
      "delivery_type": "delivery"
    },
    "total_price": "180.00",
    "delivery_price": null,
    "created_at": "2026-07-05T15:42:43.566728Z",
    "assigned_at": "2026-07-05T15:42:43.626821Z"
  }
]
```

`delivery_address` في courier response يحتوي `manual_city` و`manual_area` حتى تظهر المناطق اليدوية للمندوب.

### Status transitions

```http
PATCH /api/v1/courier/orders/{order_id}/status/
```

Allowed transitions:

| الحالي | التالي المسموح |
|---|---|
| `assigned` | `picked_up` |
| `picked_up` | `delivered` |

Request:

```json
{
  "status": "picked_up"
}
```

إذا أرسل المندوب انتقالاً غير مسموح يرجع:

```json
{
  "status": "Invalid status transition."
}
```

## Notifications

List:

```http
GET /api/v1/notifications/?unread=true&type=new_order_review&is_blocking=true
```

Notification shape:

```json
{
  "id": 20,
  "audience": "admin",
  "type": "new_order_review",
  "title": "New order requires review",
  "message": "Order #27 requires admin review.",
  "order_id": 27,
  "is_read": true,
  "is_blocking": true,
  "is_resolved": true,
  "created_at": "2026-07-05T15:42:43.568514Z"
}
```

Unread count:

```json
{
  "unread_count": 9
}
```

## Dashboard

```http
GET /api/v1/dashboard/overview/?from=2026-01-01&to=2026-12-31
```

Response shape:

```json
{
  "range": {
    "from": "2026-01-01",
    "to": "2026-12-31",
    "timezone": "UTC"
  },
  "currency": "EGP",
  "revenue": {
    "total": "793.35",
    "percentage": 11.4
  },
  "orders": {
    "total": 27,
    "completed": 5,
    "incomplete": 22,
    "completion_rate": 18.5
  },
  "customers": {
    "new": 3,
    "returning": 0,
    "return_rate": 0.0
  },
  "top_products": [
    {
      "product_id": 8,
      "name": "عرض مدارس",
      "revenue": "150.00",
      "quantity_sold": 1,
      "orders_count": 1
    },
    {
      "product_id": 41,
      "name": "فيتامين C",
      "revenue": "120.00",
      "quantity_sold": 1,
      "orders_count": 1
    }
  ],
  "active_orders": [
    {
      "id": 27,
      "number": "YM-20260705-000027",
      "customer": {
        "id": 2,
        "name": "أمينة حسن"
      },
      "total": "180.00",
      "status": "assigned",
      "created_at": "2026-07-05T15:42:43.566728Z"
    },
    {
      "id": 26,
      "number": "YM-20260705-000026",
      "customer": {
        "id": 3,
        "name": "كريم محمود"
      },
      "total": "989.00",
      "status": "pending",
      "created_at": "2026-07-05T15:42:43.512571Z"
    }
  ],
  "top_shops": [
    {
      "market_id": 2,
      "name": "متجر العروض العامة",
      "zone": "",
      "orders_count": 1,
      "average_items_per_order": 3.0,
      "revenue": "226.00"
    },
    {
      "market_id": 7,
      "name": "صيدلية الحياة - الدقي",
      "zone": "الجيزة",
      "orders_count": 1,
      "average_items_per_order": 2.0,
      "revenue": "205.10"
    }
  ]
}
```

## Integration Checklist

- أرسل `remember` صراحة في client login، مع اعتبار القيمة الافتراضية `false`.
- خزّن `accessToken`, `refreshToken`, و`session` معاً فقط عندما `session.remember=true`؛ المؤقت يتبع سياسة الذاكرة/sessionStorage أعلاه.
- استبدل access وrefresh معاً بعد كل rotation، ولا تعاود استخدام refresh القديم.
- ابعث `accessToken` في `Authorization` لكل endpoint محمي، وحدّثه تلقائياً قبل الانتهاء أو بعد `401` مرة واحدة.
- لا تعرض Home أو Offers للعميل قبل اختيار `market_region`.
- عند `general` أنشئ/استخدم عنواناً عاماً يدوياً فقط، ولا ترسل `service_city_id` في preview/create.
- لا تعتبر `manual_city="القاهرة"` مدينة خدمة؛ هي نص فقط في الطلب العام.
- عند `service_city` استخدم عنواناً بنفس المدينة المختارة.
- اعتمد على `preview` لحساب السعر، ثم نفذ `create` بنفس السلة.
- بعد `create` اقرأ الطلب من العنصر الأول في القائمة: `response[0]`.
- في عرض multi-market اعتمد على `market_sections` و`pickup_stops`، لا على `market` فقط.
- في courier UI اعرض `manual_city` و`manual_area` من `delivery_address`.
- تعامل مع `delivery_price=null` كـ “السعر يحدد لاحقاً”، وليس كخطأ.
