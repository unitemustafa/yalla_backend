# Yalla Backend

Django REST backend for the Yalla client app, representative app, and admin dashboard. PostgreSQL is the production database, Redis backs distributed throttling and Celery, Cloudinary stores media, and Firebase Cloud Messaging delivers push notifications.

## Quick start

Requires Python 3.13. PostgreSQL and Redis are required for a production-like environment; the fast local test suite uses isolated SQLite and mocks the Redis boundary.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Settings are environment-driven. Do not add a `config.local_settings` module or commit secrets. Copy `.env.example` into your secret manager/environment and replace every placeholder. Django does not automatically read `.env`; load it through your platform, shell, or container runtime.

## Verification

Fast local suite:

```powershell
.\.venv\Scripts\python.exe manage.py test --settings=config.test_settings
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.test_settings
.\.venv\Scripts\python.exe manage.py spectacular --settings=config.test_settings --file openapi.yml --validate
```

CI additionally runs the full suite on PostgreSQL, Ruff, Bandit, pip-audit, coverage with a 90% floor, migration drift, OpenAPI validation, and Django's production deployment checks.

## API and roles

- `client`: browses the catalog and manages only its own addresses, orders, devices, and notifications.
- `representative`: internal role name for delivery workers. Existing public `/api/v1/courier/` routes remain compatible.
- `admin`: application administrator. API authorization uses `role`; Django's `is_staff`/`is_superuser` flags never grant application API access.

Authentication is required by default. The reviewed public allowlist is enforced by `config/test_route_security.py`. OpenAPI is exposed at `/api/schema/` and Swagger UI at `/api/docs/`; both require an admin-role JWT. Version 1 contracts remain backward compatible.

`config/test_consumer_routes.py` is the compatibility inventory for the paths and HTTP methods currently used by `yalla_market`, `yalla_home`, and `yalla_admin`. Update that test only together with the affected consumer; an uncoordinated v1 route removal must fail CI.

Version 2 currently mirrors the same resources under `/api/v2/`, but list responses use `{count,next,previous,results}` pagination with a default page size of 50 and a maximum requested size of 100. Migrate consumers endpoint-by-endpoint; do not change version 1 list shapes.

## Project layout

- `accounts`: identity, JWT/OTP, roles, sessions and account lifecycle.
- `catalog`, `markets`, `offers`: storefront domain.
- `orders`: pricing, ownership and order lifecycle.
- `locations`: addresses, delivery coverage and geocoding.
- `notifications`: persisted inbox, FCM delivery and dispatch state.
- `dashboard`, `partners`: admin summaries and partnership workflow.
- `config`: settings, URL composition, throttling, request limits, health checks and observability.

Shared permission classes live in `accounts.permissions`. Business mutations belong in each app's `services.py`; reusable read query construction belongs in `selectors.py`. Keep API response shapes in serializers and views, and add ownership/role tests for every object endpoint.

Large write paths are intentionally separated from their public serializer/view modules. `orders.write_validation`, `markets.write_serializers`, `accounts.admin_user_serializers`, and `catalog.admin_product_serializers` contain focused write behavior while the established serializer class names remain the compatibility boundary. Admin-review and courier order views live in role-specific modules and are re-exported from `orders.views`; market admin views follow the same pattern. Management commands only parse options and orchestrate work—the reusable seed stages live in `accounts.seeders_*` and `dashboard.seeders_*`.

When extending the backend, preserve that boundary: put database-changing workflows in services or focused write mixins, query composition in selectors, and transport concerns in views/serializers. Avoid adding another long method to a facade module; create a focused module and keep the old import available when consumers or URL configuration depend on it.

## Production release

Run migrations once as a release step, then start web and worker processes independently:

```text
python manage.py migrate --noinput
gunicorn --config config/gunicorn.conf.py config.wsgi:application
celery -A config worker --loglevel=INFO
```

The container web command never runs migrations. Configure a reverse-proxy request limit matching the values in `.env.example`; application middleware cannot reject oversized chunked uploads before parsing. Logs are JSON and include `X-Request-ID`; request bodies and credentials must never be logged.

Production push delivery uses the transactional `PushOutbox`. Keep both Celery worker and beat running: the worker performs retryable FCM delivery, while beat republishes pending entries and recovers expired processing leases. A Redis/worker outage therefore delays a push but does not roll back or lose the committed business operation.

Before each release: back up PostgreSQL, test restore on a separate database, review SQL with `python manage.py sqlmigrate`, deploy migrations, deploy web/worker, run health checks, and retain the previous image. Roll back application code first; reverse a migration only after confirming it is reversible and no newer data depends on it.

The maintained API references are `docs/API_REPORT.md`, the Postman collection in `docs/`, and generated OpenAPI. Do not edit generated OpenAPI by hand.
