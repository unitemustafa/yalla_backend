# Yalla Backend: Complete Project Guide

> A practical architecture and onboarding guide for developers who are new to the codebase. The explanations deliberately include the reasoning behind the design, not only a list of files.

## 1. What This Project Is

Yalla Backend is a Django REST API that serves three main consumers:

1. The customer mobile application.
2. The delivery representative application. The code uses the name `representative`; public URLs keep the older `/courier/` wording for compatibility.
3. The administration dashboard.

The platform lets customers select a browsing region, discover markets and products available in that region, maintain delivery addresses, preview server-calculated prices, create multi-market orders, receive notifications, and track delivery. Administrators manage the catalog and operational data, review orders, quote delivery, assign representatives, and view business metrics. Representatives see only their assigned orders and move them through a restricted delivery workflow.

The production stack is:

| Concern | Technology | Responsibility |
|---|---|---|
| Web framework | Django 6 | Models, settings, migrations, middleware, and management commands |
| API layer | Django REST Framework | Authentication, permissions, serializers, views, and API responses |
| Authentication | Simple JWT | Access/refresh tokens, rotation, blacklisting, and custom session claims |
| Database | PostgreSQL | Authoritative application state and relational integrity |
| Edge and request protection | Cloudflare and Nginx | TLS termination, trusted client IPs, static/media delivery, and shared request limits |
| Media | Persistent filesystem, Nginx, and Cloudflare | Public catalog media and protected order media |
| Push notifications | Firebase Cloud Messaging | Mobile events for clients and representatives |
| API documentation | drf-spectacular | Generated OpenAPI schema and protected Swagger UI |
| Web process | Gunicorn | Threaded WSGI application server |
| Static files | WhiteNoise | Serves collected static assets |

The project is a modular monolith. Every domain runs in the same Django deployment and database, but the code is divided into Django apps with explicit responsibilities. This is an appropriate design for the current system: transactions can safely span related domain changes without introducing distributed-system complexity.

## 2. The Mental Model to Learn First

A request normally travels through these layers:

```text
Client request
    |
    v
Gunicorn / Django URL routing
    |
    v
Middleware
  - security headers
  - request correlation ID
  - request-body size limits
  - CORS / sessions / CSRF / authentication support
    |
    v
DRF authentication
  - validate JWT signature
  - reload the user from the database
  - validate account, verification, token version, and session deadline
    |
    v
DRF permissions and optional process-local rate limiting
    |
    v
View
  - coordinates the HTTP operation
  - selects the correct queryset and serializer
    |
    v
Serializer / service
  - validates untrusted input
  - enforces domain rules
  - performs an atomic mutation when required
    |
    v
PostgreSQL
  - stores the result
  - enforces foreign keys, uniqueness, and check constraints
    |
    v
transaction.on_commit callbacks
  - create or publish side effects only after the business transaction commits
    |
    v
Firebase Cloud Messaging
```

Three rules explain much of the codebase:

1. **The application role is authoritative.** API access is based on `User.role`, not `is_staff` or `is_superuser`.
2. **The selected market region controls visibility and checkout.** A customer cannot safely browse one region and submit products from another.
3. **The server owns pricing and lifecycle transitions.** Clients send IDs and intent; the backend reloads current products, variants, offers, addresses, and representatives before deciding what is valid.

## 3. Repository Layout

| Path | Primary responsibility |
|---|---|
| `accounts/` | Custom user model, roles, OTP flows, JWT sessions, profiles, account state, and shared permission classes |
| `locations/` | Service cities, delivery areas, customer addresses, coverage geometry, and Geoapify integration |
| `markets/` | Markets, market classifications/types, region selection, storefront home data, search, and likes |
| `catalog/` | Categories, subcategories, product attributes, variants, additions, images, and product likes |
| `offers/` | Offer scope, schedule, products/items, discounts, announcement metadata, and offer images |
| `orders/` | Checkout preview, server-side pricing, order creation, review, assignment, delivery state, and history |
| `notifications/` | Persisted inbox, dispatch records, FCM devices, and post-commit push delivery |
| `dashboard/` | Dashboard branding/settings, business metrics, and demo data seeders |
| `partners/` | Customer partnership applications and the admin review workflow |
| `config/` | Settings, URL composition, pagination, rate limits, request limits, health checks, logging, schema, WSGI, and ASGI |
| `docs/` | Human-maintained API/reporting documentation and the Postman collection |
| `openapi.yml` | Generated API contract; do not edit it manually |
| `.github/workflows/backend-ci.yml` | The production verification pipeline |
| `Dockerfile`, `Procfile` | Container and process definitions |

### 3.1 The local layering convention

The project is gradually separating large modules without breaking imports used by URLs or consumers:

- `views.py` handles transport concerns and may re-export views from focused modules.
- `serializers.py` owns request/response contracts and may use focused write mixins.
- `services.py` owns reusable mutations or business workflows.
- `selectors.py` owns reusable, optimized read querysets.
- `models.py` defines persisted state and database invariants.

Examples include `orders.admin_review_views`, `orders.courier_views`, `orders.write_validation`, `markets.write_serializers`, `accounts.admin_user_serializers`, and `catalog.admin_product_serializers`.

When adding a feature, follow the boundary already used by that app. Do not create a new service/repository abstraction for a one-line CRUD operation, but do not add a long transactional workflow directly to an already-large view either.

## 4. URL Structure and API Versioning

The root router is `config/urls.py`.

Public non-API endpoints include:

- `/privacy/`, `/terms/`, and `/account-deletion/` for legal pages.
- `/health/` and `/healthz/` for liveness.
- `/readyz/` for dependency readiness.
- `/share/products/<id>/`, `/share/offers/<id>/`, and `/share/markets/<id>/` for public share landing pages.

The generated schema at `/api/schema/` and Swagger UI at `/api/docs/` require an admin-role JWT. Django's admin application is installed, but `admin.site.urls` is not mounted in the root URL configuration; the product's administration surface is the role-protected dashboard API.

API resources are mounted below `/api/v1/` and `/api/v2/`. Version 2 currently reuses the same application URL modules; its intentional difference is list pagination:

```json
{
  "count": 125,
  "next": "https://example/api/v2/resource/?page=2",
  "previous": null,
  "results": []
}
```

Version 1 preserves existing unpaginated list shapes. `config.pagination.V2PageNumberPagination` activates only when the request path begins with `/api/v2/`. The default page size is 50 and the maximum requested page size is 100.

The API namespaces are:

| Namespace | Main use |
|---|---|
| `auth/` | Registration, OTP verification, login/refresh/logout, profile, availability checks, and admin user management |
| `market-region/` | Region detection, available region options, and current selection |
| `home/` | Home payload, market discovery/storefronts, search, address-filtered products, and market likes |
| `catalog/` | Admin catalog CRUD, products/variants/images/additions, notifications, and product likes |
| `offers/` | Offer discovery/admin CRUD, image upload, and notification dispatch |
| `orders/` | Client preview/create/history plus admin order operations |
| `admin/` | Focused admin order review and representative lookup actions |
| `courier/` | Assigned-order list/detail and representative-controlled transitions |
| `addresses/`, `locations/` | Customer addresses, service cities, delivery areas, coverage, and geocoding |
| `notifications/` | Inbox state and FCM device registration |
| `partners/` | Client applications and admin review |
| `dashboard/` | Overview metrics and dashboard branding/settings |

Do not casually change a v1 response. `config/test_consumer_routes.py` is the compatibility inventory for routes used by the existing customer, representative, and admin clients. A route removal or method change must be coordinated with its consumers.

The detailed endpoint and sample-payload reference lives in `docs/API_REPORT.md`. The generated machine-readable contract lives in `openapi.yml`.

## 5. Authentication, Roles, and Sessions

### 5.1 The custom user model

`accounts.User` extends Django's `AbstractUser` and adds:

- Unique email and phone.
- `role`: `admin`, `client`, or `representative`.
- Personal profile fields and avatar storage.
- Legal acceptance fields.
- Email verification state.
- Soft-deletion/anonymization fields.
- `auth_token_version` for immediate session invalidation.
- The customer's current market-region selection.

The username also has a case-insensitive database uniqueness constraint. A check constraint ensures that non-admin roles cannot carry privileged Django staff/superuser flags. Superusers created through the custom manager are forced to have the application `admin` role.

`CourierProfile` is a one-to-one extension for representative accounts. It stores the representative's vehicle data, service city, optional legacy delivery area, availability, and maximum active-order capacity.

### 5.2 Why `role` matters more than Django staff flags

Shared permission classes live in `accounts/permissions.py`:

| Permission | Allowed role |
|---|---|
| `IsAdminRole` and domain-specific admin subclasses | `admin` |
| `IsClientRole` and domain-specific client subclasses | `client` |
| `IsRepresentativeRole` | `representative` |
| `DeliveryAreaPermission` | Any authenticated user for safe reads; admin for writes |

Never authorize an API endpoint with only `is_staff` or `is_superuser`. Those flags belong to Django administration mechanics; they are not the application's business authorization model.

### 5.3 Registration and email verification

The registration flow is intentionally two-phase:

```text
POST signup
    -> normalize and validate identity fields
    -> create or safely update one unverified user
    -> hash the password
    -> issue and email a hashed OTP
    -> apply progressive resend cooldown

POST verify-email
    -> lock and load the unverified user
    -> verify OTP hash, expiry, use state, and attempt limit
    -> mark the user verified
    -> issue JWT credentials
```

The database never stores the plaintext OTP. `OneTimePassword` stores a hash, purpose, expiry, attempt count, and consumption timestamp. `OTPCooldown` prevents resend abuse with a persistent cooldown record. Public responses do not reveal whether a password-reset account exists, which reduces account enumeration.

### 5.4 Login endpoints

There are role-specific login contracts for clients, representatives, and admins. The serializer verifies credentials, account state, email verification, and the expected role. A successful representative login can make the representative available again and record an admin notification.

JWT responses use camelCase compatibility fields such as `accessToken`, `refreshToken`, and `expiresIn`.

### 5.5 Custom mobile session behavior

Simple JWT provides signing, rotation, and blacklisting. The project adds stronger database-aware checks:

- Access tokens live for at most 15 minutes.
- Refresh tokens rotate and old refresh tokens are blacklisted.
- Remembered client/representative sessions last 7 days.
- Temporary client/representative sessions have an absolute 8-hour deadline.
- Admin remembered sessions last 7 days; temporary admin sessions last 8 hours.
- Mobile tokens include session-mode and absolute-deadline claims.
- Mobile tokens include `auth_token_version`.

`DatabaseStateJWTAuthentication` reloads the user for every authenticated request. For clients and representatives it rejects a token when the account is inactive/deleted, email is unverified, the session deadline passed, or the token's version differs from the database version.

This means incrementing `auth_token_version` immediately invalidates already-issued access tokens, not only refresh tokens. `revoke_user_sessions()` increments the version and blacklists all outstanding refresh tokens.

### 5.6 Account deactivation and deletion

Deactivation revokes sessions and can send an account-disabled notification. Client deletion is an anonymization workflow, not a blind SQL delete:

- Active orders block deletion.
- Addresses referenced by orders are retained but stripped of personal data.
- Unreferenced addresses, personal notifications, devices, OTPs, and likes are removed.
- Partner-application identity data is anonymized.
- User identity fields are replaced with unique deleted placeholders.
- The password becomes unusable and the account is marked deleted/inactive/unverified.
- Tokens are invalidated.
- Avatar storage cleanup is scheduled after commit.

Transactional records survive for operational and financial integrity without retaining unnecessary personal information.

## 6. The Location and Market-Region Model

This is the most important cross-domain concept for a new developer.

### 6.1 Service cities and delivery areas

`ServiceCity` is a supported geographic market region. It can define coverage using:

1. GeoJSON polygon or multipolygon boundaries.
2. A bounding box.
3. A center point and radius fallback.

`DeliveryArea` belongs to one service city and may define a more specific coverage area plus a fixed delivery price and ETA range.

Both models can be archived instead of deleted when transactional or active relationships protect them. This avoids destroying historical references.

### 6.2 Customer addresses

An `Address` belongs to a user and records structured text, coordinates, location-provider metadata, and delivery classification.

There are two important address outcomes:

| Address outcome | Stored location | Delivery behavior |
|---|---|---|
| Fixed-area address | Service city + matching delivery area | Direct fulfillment with the area's known price |
| Manual/external address | Service city without a matching fixed area, or General manual city/area | External shipping; an admin may need to quote delivery |

The database enforces that `delivery_type=fixed_area` has a delivery area and that `delivery_type=delivery` does not. Serializer validation adds the richer rules that depend on user, region, coordinates, and active coverage.

Only one active address should be treated as default. The current write paths enforce this as an application-level invariant with atomic blocks and set-based updates; there is no conditional database uniqueness constraint on `is_default`. New address write paths must reuse the same normalization behavior, and any future high-concurrency work should explicitly revisit row locking or a database constraint.

### 6.3 Coverage evaluation

`locations.coverage.contains_point()` applies coverage in this order:

1. Optional known-city distance cap.
2. Bounding-box rejection for a quick coarse check.
3. GeoJSON polygon/multipolygon point-in-polygon evaluation.
4. Bounding-box acceptance if no usable polygon is available.
5. Center/radius fallback.
6. Legacy permissive behavior when coverage is not configured.

`matching_delivery_area()` finds an active area inside the selected service city. Never trust a client-provided delivery-area ID without checking the actual coordinates and parent service city.

### 6.4 Browsing-region selection

Each user can select either:

- `general`, with no service city; or
- `service_city`, with one active `ServiceCity`.

The database constrains valid combinations. The region endpoints can list options, return/update the current selection, and suggest a region from device coordinates.

The selected region affects:

- Visible markets.
- Visible products.
- Visible and usable offers.
- Valid customer addresses.
- Checkout validation.
- Representative eligibility for city-scoped orders.
- Notification targeting for market, product, offer, and delivery-area events.

General browsing shows general markets. Service-city browsing shows markets assigned to that city according to the rules in `markets.region`. Checkout rejects mixed or out-of-region products and offers even if a client bypasses the storefront UI.

## 7. Storefront Domain: Markets, Catalog, and Offers

### 7.1 Markets

The market hierarchy contains:

- `MarketClassification`: broad presentation grouping such as popular, featured, or normal.
- `MarketType`: bilingual type labels ordered within a classification.
- `Market`: the sellable shop/storefront.
- `MarketSubcategory`: ordered through-table assigning catalog subcategories to a market.

A market has a status, a scope (`general` or `service_city`), optional city and legacy delivery-area relationships, images, branch text, delivery-time range, types, subcategories, and customer likes.

Client querysets annotate product counts, minimum payable product prices, and per-user like state. Read paths should reuse these optimized query patterns instead of issuing per-market queries in serializers.

Markets with historical orders or protected products are archived rather than physically deleted.

### 7.2 Catalog

The catalog supports two related attribute systems:

1. Category-level attributes and options, useful for normalized reusable category metadata.
2. Product-level attributes and options, useful for product-specific choices.

The main sellable chain is:

```text
Market
  -> Product
      -> ProductVariant (authoritative price and optional SKU)
          -> VariantAttributeValue
```

An order references `ProductVariant`, not just `Product`, because price and selected options belong to the variant.

Other catalog records include classifications, categories, bilingual store subcategories, product images, and additions. A product can be popular, available/unavailable, discounted, liked, and archived.

Product image handling is a small service of its own. It validates decoded image content, maintains one primary image, supports ordering, preserves the legacy `Product.image` field, and schedules unreferenced storage deletion only after a successful database commit.

### 7.3 Offers

Offers support package, flash, percentage-discount, announcement, and delivery types. An offer includes:

- Schedule and active-day information.
- Global and per-user use limits.
- General or service-city visibility.
- Optional market/products and explicit `OfferItem` variant quantities.
- Percentage discount.
- Announcement link/CTA/priority/duration.
- Push-notification state.

`get_effective_status()` distinguishes inactive, expired, scheduled, and active behavior using the current time. Visibility also requires a valid region scope. Notification sending additionally requires active referenced markets.

Announcement offers are display/navigation content and cannot be placed in an order. Delivery offers can make delivery free; the pricing code then prevents an admin from adding a positive delivery charge.

## 8. Orders: The Core Business Workflow

Orders are the most complex domain because they combine authorization, region rules, live catalog data, discounts, delivery pricing, review, assignment, history, and notifications.

### 8.1 Why preview and create are separate

The client first calls the preview endpoint with selected variant/offer IDs and an address. The backend:

- Loads current variants, products, markets, and offers.
- Confirms they are visible in the user's selected region.
- Confirms the address belongs to the user and matches that region.
- Groups content by market.
- Calculates product prices after product discounts.
- Applies offer discounts and usage limits.
- Determines fixed or externally quoted delivery behavior.
- Returns market groups and an overall pricing summary.

The create endpoint repeats authoritative validation. A preview is informative, not a reservation: prices, availability, offer limits, or regional assignments may change between preview and create.

Never accept totals, unit prices, discounts, or delivery eligibility from the request body.

### 8.2 Multi-market order structure

One checkout creates one parent `Order`, even when it contains products from several markets. `OrderMarketSection` divides that order into per-market pickup sections:

```text
Order
  |- OrderMarketSection: Market A
  |    |- OrderItem
  |    |- OrderItem
  |    `- OrderOffer
  |
  `- OrderMarketSection: Market B
       |- OrderItem
       `- OrderOffer
```

The parent stores customer, address, authoritative lifecycle, region, fulfillment, delivery price, and total values. Each section stores its market subtotal, discount, pickup state, and order. This allows one representative to collect from multiple shops while the customer sees a single order lifecycle.

The parent `market` relation remains as a compatibility/primary-market field. New multi-market code should use `market_sections` when it needs the complete set of shops.

### 8.3 Price calculation

At a high level:

```text
discounted unit price = variant price * (100 - product discount) / 100
product line subtotal = discounted unit price * quantity
offer discount        = eligible offer percentage * covered product subtotal
order total           = subtotal - discounts + delivery price
```

Money uses `Decimal`, never binary floating-point values. The backend snapshots each order item's `unit_price`, so later catalog price changes do not rewrite history.

For a fixed delivery area, the known delivery price is applied once at the parent order level. For external shipping, delivery can initially be unknown (`null`) and quoted later. A free-delivery offer makes the parent delivery price zero.

### 8.4 Review and delivery state machines

Order review is separate from delivery status:

```text
review_status:
  pending_review -> approved
  pending_review -> rejected
```

Approval changes the operational status from `pending` to `confirmed`. Rejection changes it to `cancelled` and records reviewer/reason metadata.

The intended delivery lifecycle is:

```text
pending
  -> confirmed                 (admin approval)
      -> assigned              (admin assigns representative)
          -> picked_up         (representative action)
              -> delivered     (representative action)
              -> failed_delivery

Cancellation is a controlled terminal path.
```

Terminal states are `delivered`, `failed_delivery`, and `cancelled`. Transition maps in `orders.services` are the authoritative rules for admin and representative actions. Do not let a generic serializer update `status` freely.

### 8.5 Delivery quotes

External shipping has its own state:

- `pending_quote`: no authoritative price yet.
- `awaiting_customer_approval`: admin provided a price and explicitly requested approval.
- `quoted`: price is final, either immediately or after the customer accepted it.
- `not_required`: fixed/direct delivery does not use the external quote flow.

When an admin changes a quote, the backend recalculates total price and writes an `OrderEvent`. If approval is requested, the customer receives a lifecycle notification. Only the owning customer can accept the quote.

### 8.6 Representative assignment

An order must be approved and confirmed/assigned before assignment. The selected user must:

- Have role `representative`.
- Be active and not deleted.
- Have an available `CourierProfile`.
- Match the required service city for a city-scoped order.
- Be below `max_active_orders`.

Assignment and unassignment run in transactions with row locks. Assignment writes timestamps/events and notifies both relevant audiences. An order cannot be unassigned after pickup or after reaching a terminal state.

### 8.7 Order history

`OrderEvent` is the audit trail. It records event type, old/new status, actor, note, structured metadata, and creation time. Events cover creation, review, status changes, assignment, unassignment, delivery-price changes, delivery-quote actions, and cancellation.

Notifications are deduplicated against order events where appropriate. If you add a new lifecycle mutation, ask four questions:

1. Is the row locked?
2. Is the transition explicitly allowed?
3. Is an `OrderEvent` recorded?
4. Are side effects scheduled after commit?

## 9. Notifications and Reliable Push Delivery

### 9.1 Persisted notification inbox

`Notification` stores durable in-app messages for admin, client, or courier audiences. A notification can reference an order/event, offer, product, dispatch, or direct recipient. It also stores arbitrary navigation/event data and read/resolution state.

Blocking admin notifications are used for work that needs attention, such as a new order review. Approving/rejecting an order resolves that blocker instead of simply deleting operational history.

`ClientDevice` stores unique FCM tokens, platform, activity state, and last-seen time. Invalid/rejected tokens can be deactivated by delivery logic.

### 9.2 Dispatch records

Offer, product, market, and delivery-area broadcast workflows use dispatch models. These records provide idempotency, status, requester, recipient count, notification count, completion time, and error information.

Broadcast recipient selection is region-aware. A notification about a city-scoped offer or market should not be sent to unrelated customers.

### 9.3 Post-commit push delivery

Directly sending to Firebase inside a database transaction is unsafe because the push can succeed while the database later rolls back. Push callbacks are therefore registered with `transaction.on_commit`:

```text
Business mutation
    -> Notification / domain data
COMMIT
    -> send FCM
```

Firebase failures are logged and do not roll back the committed business operation. The mobile applications refresh their persisted notification inbox when they reopen, which remains the fallback when a push cannot be delivered.

## 10. Dashboard and Partner Applications

### 10.1 Dashboard

`DashboardSettings` stores editable branding such as colors, font, name, tagline, and logo.

Dashboard overview metrics are built in `dashboard.services` for a requested date range. They include:

- Revenue from delivered orders.
- Total/completed/incomplete orders and completion rate.
- New and returning customer metrics.
- Top products by delivered revenue.
- Recent active orders.
- Top shops, including multi-market section revenue and legacy-order compatibility.

Queries use aggregates, annotations, `select_related`, and `prefetch_related`. When changing metrics, preserve both correctness and query count; dashboard endpoints can become expensive quickly.

### 10.2 Partner applications

Only clients may submit partnership applications. The model stores business/contact information, applicant role, trade-license state, notes, reviewer metadata, and one of four states:

```text
pending -> in_review -> approved
                     -> rejected
```

Submission creates an admin notification. Final review resolves that notification. First-time approval schedules a high-priority client push. The main status update is authoritative; secondary notification/audit helpers are designed not to unnecessarily roll back a valid review decision.

## 11. Database Design and Data Integrity

The database is not a passive storage bucket. It is the final line of defense for invariants that must remain true regardless of which code path writes data.

Important examples include:

- Case-insensitive username and bilingual subcategory/type uniqueness.
- Valid user market-region combinations.
- No staff/superuser privileges on non-admin roles.
- A fixed-area address/order must reference a delivery area.
- Non-negative delivery prices, section subtotals, and discounts.
- One primary product image per product.
- One order-market section for each market in an order.
- Unique offer use per section/order combination.
- Deduplicated notifications per dispatch recipient or order event.
- Exactly one valid target shape for each push-outbox entry.

Use `PROTECT` where historical rows must prevent deletion, `CASCADE` for true owned children, and `SET_NULL` when a historical record can remain meaningful after an optional source disappears. Follow the existing relationship's semantics rather than choosing an `on_delete` behavior mechanically.

### 11.1 Transactions and locking

Use `transaction.atomic()` when multiple writes form one business operation. Use `select_for_update()` when two requests could concurrently mutate the same authoritative row, for example:

- Verifying an OTP.
- Creating an order for an account whose state may change.
- Reviewing an order.
- Quoting delivery.
- Assigning a representative.
- Changing a default address.
- Updating an account lifecycle state.

An atomic block alone does not prevent lost updates; the row lock is what serializes competing writers.

### 11.2 Query efficiency

The main optimized selectors demonstrate the expected pattern:

- Use `select_related` for single-valued foreign keys.
- Use `prefetch_related`/`Prefetch` for collections.
- Use `Exists`, `Count`, `Sum`, `Min`, `Subquery`, and `Coalesce` for database-side calculations.
- Do not perform database queries in serializer loops when the queryset can preload or annotate the data.
- Use pagination for growing v2 collections.

`orders.selectors.order_queryset()` is a good example of building one reusable read graph for rich order responses.

## 12. API and Validation Conventions

### 12.1 Authentication by default

DRF's global default permission is `IsAuthenticated`. Public endpoints must explicitly use `AllowAny` and are audited by `config/test_route_security.py`. Treat adding a public route as a security decision, not a convenience.

### 12.2 Serializer responsibilities

Serializers are used for more than model conversion. They:

- Normalize legacy/camelCase request shapes.
- Validate ownership and active status.
- Resolve related IDs to current database rows.
- Enforce cross-field domain rules.
- Produce stable consumer-facing response shapes.

Do not move authorization entirely into a serializer. Views/permissions must still restrict the endpoint, while serializers validate object-specific rules.

### 12.3 Error and throttle behavior

DRF validation errors keep standard field-oriented response shapes. Rate-limit errors are normalized to:

```json
{
  "code": "rate_limited",
  "detail": "Too many requests. Try again later.",
  "retry_after_seconds": 30
}
```

The response also includes `Retry-After`.

### 12.4 Media validation

Images are verified by decoding their metadata with Pillow. Supported formats are JPEG, PNG, and WebP. The validator checks dimensions, total pixels, extension/content agreement, and MIME/content agreement. Never trust only the request's filename or content type.

## 13. Rate Limiting and Abuse Protection

Nginx provides the shared production request limit before traffic reaches Django. Django also includes an optional process-local limiter for focused development and tests. Policies can use fixed or sliding windows and identities such as IP, authenticated user, normalized email/phone identifier, refresh-token fingerprint, or a global provider key.

Modes are:

- `off`: skip the application limiter; required for the multi-worker production deployment.
- `observe`: evaluate and report behavior without full enforcement.
- `enforce`: reject requests that exceed policy.

The application limiter is intentionally not shared between Gunicorn workers. Nginx is therefore authoritative in production. Identity values and tokens are converted into HMAC fingerprints before being used as limiter keys.

Proxy headers are trusted only when the socket peer belongs to configured proxy CIDRs. This prevents arbitrary callers from spoofing their source IP.

Detailed deployment notes live in `docs/RATE_LIMITING.md`.

## 14. Configuration and Runtime Environments

Settings are environment-driven in `config/settings.py`. A local `.env` is loaded only when `APP_ENV=development`, and it never overrides variables already provided by the shell.

Important groups are:

| Group | Variables |
|---|---|
| Core security | `APP_ENV`, `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS` |
| Database | `DATABASE_URL` |
| Rate limiting | `RATE_LIMIT_MODE`, `RATE_LIMIT_KEY_SECRET`, trusted proxy/header and policy variables |
| Firebase | `FIREBASE_SERVICE_ACCOUNT_BASE64` or `FIREBASE_SERVICE_ACCOUNT_JSON` |
| Media | `PUBLIC_MEDIA_ROOT`, `PRIVATE_MEDIA_ROOT`, `MEDIA_URL`, `PRIVATE_MEDIA_X_ACCEL_REDIRECT` |
| API cache | `API_CACHE_ENABLED` and cache timeout/observability variables |
| Email | `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` |
| Geocoding | `GEOAPIFY_API_KEY` and timeout variables |
| Request limits | `API_MAX_REQUEST_BODY_SIZE`, `API_SINGLE_UPLOAD_REQUEST_SIZE`, `API_PRODUCT_UPLOAD_REQUEST_SIZE` |
| Web process | `PORT`, `WEB_CONCURRENCY`, `GUNICORN_THREADS`, timeout/keepalive/max-request variables |

Production settings fail fast when important requirements are unsafe or absent. Production requires, among other things, a strong secret, exact allowed hosts, HTTPS CORS origins, and a PostgreSQL URL. Nginx supplies the shared production request limits.

### 14.1 Storage behavior

All environments use filesystem storage. Validated uploads are normalized to metadata-free WebP files with UUID names. Public files use `MEDIA_URL`; order images and delivery proofs live in a separate private root and are served only after Django authorization through Nginx `X-Accel-Redirect`. Tests use temporary local media/static directories and leave no artifacts in the repository.

### 14.2 Health and observability

Liveness reports process health and deployment revision without checking dependencies. Readiness checks the database.

Every request receives a safe `X-Request-ID`, accepting a valid caller-provided ID or generating one. Logs are JSON and include this correlation ID. The formatter redacts token/password/OTP-like values and the middleware does not log request bodies.

### 14.3 Request size limits

Middleware rejects an oversized request with declared `Content-Length` before Django parses it. Product multipart routes have a larger limit than normal uploads. The reverse proxy must enforce matching limits because application middleware cannot reject an oversized chunked stream before parsing.

## 15. Local Development

The supported Python version is 3.13.

### 15.1 Create an environment

Linux/macOS example:

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
```

Create `.env` from the project's environment template when available. If the template is not present in your checkout, derive the required local values from the configuration table above and never commit secrets.

For a production-like local run, provide PostgreSQL. Then run:

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

The fast isolated test suite does not require external PostgreSQL:

```bash
.venv/bin/python manage.py test --settings=config.test_settings
```

### 15.2 Migrations

After a model change:

```bash
.venv/bin/python manage.py makemigrations
.venv/bin/python manage.py sqlmigrate <app_name> <migration_number>
.venv/bin/python manage.py migrate
```

Review generated migrations before running them. Consider existing production rows, defaults, backfills, indexes, reversibility, and locking cost. A syntactically valid migration is not automatically operationally safe.

Check for accidental model/migration drift with:

```bash
.venv/bin/python manage.py makemigrations --check --dry-run --settings=config.test_settings
```

### 15.3 Seed commands

`seed_data` creates/update idempotent fake data for all major tables:

```bash
.venv/bin/python manage.py seed_data
```

`seed_demo_data` performs a destructive reset and creates a richer Egyptian demo dataset. It deliberately requires explicit confirmation flags:

```bash
.venv/bin/python manage.py seed_demo_data --reset --yes-delete-all
```

Never run the destructive command against a database you care about. It refuses non-debug operation unless an additional production-risk flag is supplied; that flag is a final guard, not permission to use production data casually.

Other operational commands include:

```bash
.venv/bin/python manage.py cleanup_unverified_users --dry-run
.venv/bin/python manage.py check_rate_limit
```

`cleanup_unverified_users` removes only expired pending mobile registrations;
it never deletes rows from the user table. Production installs run it hourly
through `yalla-auth-cleanup.timer`.

## 16. Testing and Continuous Integration

Tests use Django's built-in test runner and DRF test utilities. The local test settings use in-memory SQLite, a local-memory email backend, fast password hashing, temporary storage, and disabled distributed rate limiting.

Run a focused app test while developing:

```bash
.venv/bin/python manage.py test orders --settings=config.test_settings
.venv/bin/python manage.py test accounts.tests_sessions --settings=config.test_settings
```

Run the full local suite before handing off a broad backend change:

```bash
.venv/bin/python manage.py test --settings=config.test_settings
.venv/bin/python manage.py makemigrations --check --dry-run --settings=config.test_settings
.venv/bin/python manage.py spectacular --settings=config.test_settings --file openapi.yml --validate
```

CI runs with PostgreSQL 17 and verifies:

- Ruff syntax/high-confidence lint checks.
- Migration drift.
- Django system checks.
- Full test suite on PostgreSQL.
- At least 90% non-test/non-migration coverage.
- OpenAPI generation/validation and no uncommitted schema diff.
- Bandit security checks.
- Dependency vulnerability audit.
- Django production deployment checks.

SQLite is useful for speed, but PostgreSQL CI is authoritative for database constraints and behavior. A feature that passes locally can still fail on PostgreSQL if it relies on SQLite-specific behavior.

### 16.1 What to test for every protected object endpoint

At minimum, cover:

1. Unauthenticated request.
2. Wrong role.
3. Correct role and happy path.
4. Attempt to access or mutate another user's object.
5. Invalid/archived/inactive related rows.
6. Important transaction/state transition failures.
7. Expected response shape for both API versions when lists are involved.

For order and notification changes, also test idempotency and duplicate side-effect behavior.

## 17. Production Deployment

The container runs as a non-root application user. The Hostinger Compose workflow runs migrations and collects static files before Gunicorn; platforms using the Procfile keep the release step separate.

Run processes separately:

```text
release: python manage.py migrate --noinput
web:     gunicorn --config config/gunicorn.conf.py config.wsgi:application
```

Gunicorn uses threaded workers so bounded image processing does not block unrelated requests. Worker/thread counts and timeouts are environment-configurable.

Safe release sequence:

1. Back up PostgreSQL.
2. Prove that the backup can be restored separately.
3. Review migration SQL and data assumptions.
4. Run migrations once as the release step.
5. Deploy the web process from the reviewed application version.
6. Check liveness and readiness.
7. Exercise a minimal authenticated smoke test.
8. Monitor structured logs, request IDs, queue depth, and outbox failures.
9. Retain the previous image for application rollback.

Roll back application code before considering migration reversal. Reverse a migration only when it is known to be reversible and no newer data depends on it.

## 18. How to Add a Feature Safely

Use this sequence as a junior-friendly checklist.

### Step 1: Find the owning domain

Do not place a feature in `config` merely because several apps use it. Identify which app owns the persisted business concept. Cross-domain orchestration can import a focused public service from that app.

### Step 2: Read nearby code and tests

Find the closest existing endpoint, serializer, service, and tests. Reuse naming, response shapes, permission classes, transaction style, and query patterns.

### Step 3: Define the contract

Write down:

- Who may call the endpoint?
- What fields are untrusted?
- Which related rows must be active/owned/in-scope?
- What response shape do v1 consumers expect?
- Does v2 pagination apply?
- Which errors are client-actionable?

### Step 4: Model invariants at the right layers

- Database constraint: invariant must survive every write path.
- Serializer validation: user-friendly cross-field or request-specific error.
- Permission: endpoint-level role restriction.
- Service/state machine: reusable transition/business workflow.
- View: HTTP orchestration only.

### Step 5: Design concurrency behavior

If two requests can update the same state, use an atomic transaction and lock the authoritative rows. Re-check the rule after acquiring the lock.

### Step 6: Design side effects

Write authoritative data first. Use `transaction.on_commit()` for notifications, storage deletion, and task publication. Use the push outbox for reliable mobile delivery.

### Step 7: Optimize reads deliberately

Inspect serializer access and preload every relation used across a collection. Add an index only when the query pattern justifies it.

### Step 8: Test security and behavior

Add ownership, wrong-role, invalid-state, concurrency/idempotency, and success tests. Regenerate and validate OpenAPI when the contract changes.

## 19. Common Mistakes to Avoid

### Mistake: trusting IDs because the frontend filtered them

The frontend is not a security boundary. Reload the object and validate owner, role, active/archive state, parent relation, and region.

### Mistake: authorizing with `is_staff`

Use the shared role permission classes. Application admins are defined by `User.role=admin`.

### Mistake: calculating an order total from request values

Only accept selection IDs, quantities, and intent. Load current database prices/discounts and calculate with `Decimal`.

### Mistake: treating preview as a locked quote

Create must revalidate everything because catalog and offer state can change after preview.

### Mistake: reading only `Order.market`

That field is kept for compatibility. Use `market_sections` for the complete multi-market picture.

### Mistake: bypassing region helpers

Storefront filtering and checkout rules must agree. Reuse `markets.region` helpers instead of inventing a slightly different filter.

### Mistake: sending push before commit

The database could roll back after the user received a false notification. Use on-commit scheduling and the outbox pattern.

### Mistake: using `transaction.atomic()` without a row lock

Atomicity groups writes; it does not automatically prevent another request from reading and overwriting the same state.

### Mistake: deleting operational entities unconditionally

Markets, offers, cities, areas, and products can be referenced by historical orders or dispatches. Respect `get_deletion_mode()`, archive behavior, and `PROTECT` relationships.

### Mistake: introducing N+1 queries in a serializer

Inspect collection access and update the queryset with related loading or annotations.

### Mistake: editing `openapi.yml` by hand

Change code/schema annotations, regenerate the file, validate it, and commit the generated diff.

## 20. Debugging Playbook

### An authenticated request unexpectedly returns 401

Check, in order:

1. Token expiry/signature.
2. User still exists.
3. User is active and not soft-deleted.
4. User is verified.
5. Token `auth_token_version` equals the database value.
6. Temporary mobile session absolute deadline has not passed.
7. Refresh token was not blacklisted after rotation/logout/password change.

### A request returns 403

Inspect the view's `permission_classes` and the user's application `role`. Do not "fix" it by changing Django staff flags.

### Products or offers disappear

Check current user region selection, market scope/status/city assignment, product availability/archive state, offer schedule/status/scope/use limits, and active referenced markets.

### An address is rejected

Check current region mode, owner, active state, service city, manual city/area requirements, coordinate pair completeness, city coverage, matching delivery area, and the delivery area's active/parent-city state.

### An order cannot be assigned

Check review status, operational status, representative role/activity/deletion, courier profile, availability, service-city match, and active-order capacity.

### A push is missing

Check, in order:

1. Was a persisted `Notification` created?
2. Did the surrounding database transaction commit?
3. Is Firebase configured?
4. Does the recipient have active device tokens?
5. Do application logs show an FCM error?

Use the request ID from the response to correlate JSON logs.

### Readiness returns 503

Inspect the response's `checks.database` value and PostgreSQL container health.

## 21. Key Source Files for Onboarding

Read these in order during the first few days:

1. `README.md` — short operational summary.
2. `config/settings.py` and `config/urls.py` — global runtime and route map.
3. `accounts/models.py`, `accounts/permissions.py`, and `accounts/authentication.py` — identity/security model.
4. `markets/region.py` — cross-domain visibility rules.
5. `locations/models.py`, `locations/coverage.py`, and the address serializer — delivery geography.
6. `catalog/models.py`, `markets/models.py`, and `offers/models.py` — storefront data.
7. `orders/models.py`, `orders/services.py`, `orders/selectors.py`, and focused order views — main business lifecycle.
8. `notifications/models.py`, `notifications/services.py`, and `notifications/push.py` — persisted notifications and post-commit push delivery.
9. `dashboard/services.py` — aggregation/query patterns.
10. Relevant tests — executable documentation for permissions, state machines, and compatibility.

## 22. Glossary

| Term | Meaning in this project |
|---|---|
| Client | Customer account using the shopping application |
| Representative / courier | Delivery worker; `representative` is the internal role and `courier` remains in public compatibility URLs |
| Service city | A supported city-level market region |
| Delivery area | A fixed-price delivery zone inside a service city |
| General region | Browsing mode for general markets outside a selected service city |
| Fixed-area delivery | Direct delivery with an authoritative known delivery price |
| External shipping | Delivery requiring a manual or externally determined quote |
| Market section | The portion of one parent order belonging to one market |
| Review status | Admin acceptance/rejection state, separate from delivery status |
| Order event | Immutable-ish lifecycle/audit record for an order mutation |
| Dispatch | Persistent record of a broadcast notification operation |
| Outbox | Database-backed queue of push intents published after commit |
| Selector | Reusable optimized read-query construction |
| Service | Reusable business mutation/workflow |

## 23. First-Week Onboarding Checklist

- Run the isolated test suite successfully.
- Create local seed data and log in as each role.
- Trace one authenticated request from URL to response.
- Trace signup, OTP verification, login, refresh, and logout.
- Select General and service-city regions and compare visible storefront data.
- Create one fixed-area address and one external/manual address.
- Preview and create a multi-market order.
- Approve, quote if necessary, assign, pick up, and deliver that order.
- Inspect its `OrderEvent` rows and resulting notifications.
- Inspect a push-outbox row from pending through completion in a worker-enabled environment.
- Run a focused test, the full test suite, migration drift check, and OpenAPI validation.
- Before the first code change, identify the domain owner, permissions, database invariant, transaction boundary, and required consumer compatibility.

---

This guide explains architecture and development intent. For exact endpoint payloads use `docs/API_REPORT.md`; for the generated API contract use `openapi.yml`; for current rate-limit deployment values use `docs/RATE_LIMITING.md`. When documentation and executable behavior disagree, verify the code and tests, then update both the implementation contract and the documentation in the same change.
