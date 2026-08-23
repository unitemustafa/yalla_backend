# Yalla Backend

Production-ready REST API for the Yalla commerce and delivery platform. It
serves the customer application, delivery representative application, and
administration dashboard from a single versioned backend.

The platform covers authentication, regional storefronts, catalog management,
offers, checkout and order lifecycles, delivery assignment, notifications, and
administrative reporting.

## Highlights

- JWT authentication with refresh-token rotation and server-side revocation
- Role-based access for customers, representatives, and administrators
- Region-aware markets, catalogs, offers, addresses, and delivery pricing
- Multi-market orders with authoritative pricing and audited status changes
- Persistent notifications with Firebase Cloud Messaging delivery
- Nginx shared-memory request limiting for production traffic
- Versioned REST APIs with an OpenAPI schema and protected Swagger UI
- Health and readiness endpoints for production orchestration
- Structured JSON logs with request IDs
- Automated security, migration, schema, and test checks in CI

## Technology stack

| Area | Technology |
| --- | --- |
| Web framework | Django 6 and Django REST Framework |
| Authentication | Simple JWT with custom database-state validation |
| Database | PostgreSQL |
| Request limiting | Nginx shared memory |
| Push delivery | Synchronous Firebase delivery |
| Media storage | Persistent filesystem, Nginx, and Cloudflare CDN |
| Push notifications | Firebase Cloud Messaging |
| API documentation | drf-spectacular and OpenAPI |
| Application server | Gunicorn |
| CI and quality | GitHub Actions, Ruff, Bandit, pip-audit, and Coverage.py |

## Getting started

### Prerequisites

- Python 3.13
- PostgreSQL

### 1. Create a virtual environment

On Linux or macOS:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

On Windows PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

### 2. Configure the environment

Create a `.env` file in the project root. The following configuration is
enough for normal local development after creating a PostgreSQL database named
`yalla`:

```dotenv
APP_ENV=development
DEBUG=True
SECRET_KEY=replace-this-with-a-local-development-secret
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/yalla
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOW_ALL_ORIGINS=True
RATE_LIMIT_MODE=off
PUSH_DELIVERY_ASYNC=False
```

Development automatically loads `.env` without overriding variables already
provided by the shell. The file is ignored by Git and must never contain
production credentials committed to the repository.

### 3. Prepare and run the application

```bash
python manage.py migrate
python manage.py runserver
```

The API is available at `http://127.0.0.1:8000/api/v1/`.

### 4. Add optional development data

Use the idempotent seed command to populate the database with test data:

```bash
python manage.py seed_data
```

For the richer demonstration dataset, use the reset command below. It deletes
all existing application data before seeding and must only be used with a
disposable local database:

```bash
python manage.py seed_demo_data --reset --yes-delete-all
```

## API access

Authentication is required by default. Send the access token in each protected
request:

```http
Authorization: Bearer <access-token>
```

The application has three roles:

| Role | Purpose |
| --- | --- |
| `client` | Browses the storefront and manages personal addresses, orders, devices, and notifications |
| `representative` | Handles assigned deliveries; existing public routes retain the `/courier/` name |
| `admin` | Manages application data, operations, and reporting |

Application authorization is based on `role`. Django's `is_staff` and
`is_superuser` flags do not grant access to application API endpoints.

### Useful endpoints

| Endpoint | Description | Access |
| --- | --- | --- |
| `/health/` | Process liveness | Public |
| `/readyz/` | Database readiness | Public |
| `/api/schema/` | OpenAPI schema | Admin JWT |
| `/api/docs/` | Swagger UI | Admin JWT |
| `/api/v1/` | Stable consumer API | Authenticated by default |
| `/api/v2/` | Paginated API migration path | Authenticated by default |

Version 1 remains the compatibility boundary for the current Yalla consumers.
Version 2 exposes the same resources while list endpoints return
`{count, next, previous, results}` with a default page size of 50 and a maximum
requested page size of 100.

## Project structure

| Path | Responsibility |
| --- | --- |
| `accounts/` | Users, JWT and OTP flows, roles, sessions, and account lifecycle |
| `catalog/` | Products, variants, additions, categories, and product media |
| `markets/` | Storefronts, classifications, and regional selection |
| `offers/` | Packages, discounts, announcements, and delivery offers |
| `orders/` | Pricing, checkout, ownership, assignment, and order lifecycle |
| `locations/` | Addresses, service cities, delivery areas, coverage, and geocoding |
| `notifications/` | Notification inbox, FCM delivery, and transactional push outbox |
| `dashboard/` | Administrative summaries, reporting, and demo data |
| `partners/` | Partnership application workflow |
| `config/` | Settings, routing, rate limits, request limits, schema, health, and observability |
| `docs/` | Maintained API and operational references |

Business mutations belong in app-level services or focused write modules.
Reusable read queries belong in selectors, while serializers and views own the
HTTP contract. Preserve existing imports and version 1 response shapes when
splitting large modules or introducing version 2 behavior.

## Push delivery

The production stack sends Firebase notifications synchronously and does not
run a broker or background worker. Push failures are logged without rolling
back the business request.

## Environment configuration

The most important production variables are listed below. Optional timeout,
request-size, Gunicorn, and rate-policy variables have safe defaults in
`config/settings.py`.

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | Use `production` to enable production security requirements |
| `SECRET_KEY` | Unique secret with at least 50 characters in production |
| `DATABASE_URL` | PostgreSQL connection URL |
| `ALLOWED_HOSTS` | Comma-separated production host names |
| `CORS_ALLOWED_ORIGINS` | Comma-separated HTTPS dashboard origins |
| `RATE_LIMIT_MODE` | Keep `off` when Nginx request limiting is enabled |
| `PUSH_DELIVERY_ASYNC` | Keep `False` for direct Firebase delivery |
| `API_CACHE_ENABLED` | Keep `False` in the Redis-free production stack |
| `PUBLIC_MEDIA_ROOT` / `PRIVATE_MEDIA_ROOT` | Persistent public and protected media directories |
| `MEDIA_URL` | Public media base URL under the API domain |
| `FIREBASE_SERVICE_ACCOUNT_BASE64` | Preferred Base64-encoded Firebase service-account JSON |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS` | SMTP relay connection used for OTP email |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | SMTP login and secret used for OTP email |
| `DEFAULT_FROM_EMAIL` | Verified sender address used for outbound OTP email |
| `GEOAPIFY_API_KEY` | Reverse-geocoding integration key |

Production must use exact HTTPS origins, must not enable debug mode, and must
never enable `AUTH_OTP_INCLUDE_IN_RESPONSE`. See
[`docs/RATE_LIMITING.md`](docs/RATE_LIMITING.md) for the rate-limiter rollout
and rollback procedure.

## Testing and verification

The fast local suite uses isolated in-memory SQLite, local media directories,
and a mocked Redis boundary:

```bash
python manage.py test --settings=config.test_settings
python manage.py makemigrations --check --dry-run --settings=config.test_settings
python manage.py spectacular --settings=config.test_settings --file openapi.yml --validate
ruff check .
```

CI additionally runs the full suite against PostgreSQL, verifies the committed
OpenAPI document, enforces at least 90% coverage, scans the code with Bandit,
audits Python dependencies, and runs Django's production deployment checks.

When changing public routes, update consumers together with the compatibility
inventory in `config/test_consumer_routes.py`. When changing the API schema,
regenerate `openapi.yml`; do not edit the generated document manually.

## Production deployment

Run migrations once as a release step, then start the web, worker, and scheduler
processes independently:

```bash
python manage.py migrate --noinput
gunicorn --config config/gunicorn.conf.py config.wsgi:application
celery -A config worker --loglevel=INFO
celery -A config beat --loglevel=INFO
```

The provided `Dockerfile` starts only the web process and intentionally does
not run migrations.

For the production Docker stack, copy `.env.production.example` to
`.env.production`, replace every placeholder, install the TLS files described
in `docs/HOSTINGER_KVM_DEPLOYMENT.md`, and run:

```bash
./deploy/production-up.sh
```

On a new Ubuntu 24.04 Hostinger VPS, `deploy/hostinger-bootstrap.sh` installs
Docker and prepares persistent storage. Later releases can be pulled from the
GitHub `main` branch with `deploy/production-update.sh`; it creates a database
backup before updating. Use `deploy/backup.sh --with-media` when a release also
needs a local media archive.

The Compose stack contains Nginx, Django, PostgreSQL, persistent media, and
static files. The admin dashboard and Flutter applications remain independent
clients and connect over HTTPS through `api.<domain>`; public media lives at
`api.<domain>/media/`.

Before every release, back up PostgreSQL, verify that the backup can be restored
to a separate database, review migration SQL, deploy migrations, deploy all
processes, and check `/health/` and `/readyz/`. Configure the reverse proxy with
request-size limits matching the application settings, and retain the previous
application image for rollback.

## Additional documentation

- [`docs/API_REPORT.md`](docs/API_REPORT.md) — detailed endpoint and integration reference
- [`docs/RATE_LIMITING.md`](docs/RATE_LIMITING.md) — optional application rate-limiter internals
- [`docs/Yalla System APIs.postman_collection.json`](docs/Yalla%20System%20APIs.postman_collection.json) — Postman collection
- [`openapi.yml`](openapi.yml) — generated OpenAPI contract
