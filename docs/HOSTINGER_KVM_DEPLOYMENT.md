# Hostinger KVM deployment

This deployment runs the backend API independently. The admin dashboard and
mobile applications are API consumers and are not part of this Compose stack.
PostgreSQL, both Redis instances, public media, private order media, and static
files stay outside the checkout, so rebuilding the backend image does not
remove persistent data.

## Quick start from GitHub

Replace `VPS_IP` with the server address shown by Hostinger. These commands are
intended for a new Ubuntu 24.04 VPS:

```bash
ssh root@VPS_IP
apt-get update
apt-get install -y git
git clone https://github.com/unitemustafa/yalla_backend.git /opt/yalla_backend
cd /opt/yalla_backend
./deploy/hostinger-bootstrap.sh
cp .env.production.example .env.production
chmod 600 .env.production
nano .env.production
```

The bootstrap script installs Docker Engine and the Compose plugin from
Docker's official Ubuntu repository, enables Docker at boot, and creates the
persistent paths under `/srv/yalla`. It is safe to run again after Docker has
already been installed.

Never commit `.env.production`, a Firebase service-account file, a TLS private
key, or any other production credential to GitHub.

## Production configuration

1. Generate three independent values and paste them into `POSTGRES_PASSWORD`,
   `SECRET_KEY`, and `RATE_LIMIT_KEY_SECRET` in `.env.production`:

   ```bash
   openssl rand -hex 32
   openssl rand -hex 32
   openssl rand -hex 32
   ```

2. Replace every `example.com` value and every `replace-with-...` placeholder.
   For the domain visible in the Hostinger/Cloudflare setup, the core values
   are:

   ```dotenv
   DOMAIN=drmustafa.dev
   ALLOWED_HOSTS=api.drmustafa.dev
   CORS_ALLOWED_ORIGINS=https://drmustafa.dev
   CSRF_TRUSTED_ORIGINS=https://api.drmustafa.dev,https://drmustafa.dev
   ```

   If the React dashboard is hosted at another HTTPS origin, add that exact
   origin to both comma-separated origin lists where appropriate. Keep
   `DEBUG=False` and `AUTH_OTP_INCLUDE_IN_RESPONSE=False`. Copy the real
   `FIREBASE_SERVICE_ACCOUNT_BASE64`, SMTP, sender-address, and Geoapify values
   from the secure production configuration; do not copy the development
   `.env` file to GitHub.

3. Create a Cloudflare Origin CA certificate that covers
   `api.drmustafa.dev` and `media.drmustafa.dev`. Paste the certificate and
   private key on the VPS, then restrict the key permissions:

   ```bash
   nano /srv/yalla/tls/origin.pem
   nano /srv/yalla/tls/origin.key
   chmod 644 /srv/yalla/tls/origin.pem
   chmod 600 /srv/yalla/tls/origin.key
   ```

4. In Cloudflare, create proxied `A` records named `api` and `media` pointing
   to the VPS IP, and set SSL/TLS encryption mode to **Full (Strict)**.

5. In the Hostinger VPS firewall, allow inbound TCP 22, 80, and 443. Restrict
   port 22 to the administrator's IP when practical. PostgreSQL and Redis are
   private Compose services and must not be published.

If `172.30.0.0/24` conflicts with an existing host network, change both the
Compose subnet and `RATE_LIMIT_TRUSTED_PROXY_CIDRS` to the same private subnet.

## First cutover

1. Enable Hostinger daily backups and take a manual snapshot.
2. Confirm no placeholders remain without printing the complete secret-bearing
   configuration:

   ```bash
   grep -nE 'replace-with|example\.com' .env.production
   ```

   The expected output is empty.
3. Run `./deploy/production-up.sh`. It validates Compose, builds the backend,
   runs migrations and static collection, starts every service, and waits for
   health checks to pass.
4. Verify the deployment:

   ```bash
   docker compose --env-file .env.production ps
   curl --fail --silent --show-error https://api.drmustafa.dev/healthz/
   curl --fail --silent --show-error https://api.drmustafa.dev/readyz/
   ```

5. Run
   `docker compose --env-file .env.production exec django python manage.py audit_media`.
6. Verify `/healthz/`, `/readyz/`, Celery worker/beat status, public media, and
   protected order media before moving traffic.

The initial Cloudinary retirement assumes old remote media is disposable. Only
after the snapshot and database backup, clear missing references with:

```bash
docker compose --env-file .env.production exec django python manage.py audit_media --clear-missing
```

The command is dry-run by default. `--delete-orphans` is a separate explicit
operation.

## Cloudflare

- Set SSL/TLS mode to **Full (Strict)**.
- Proxy the API and media DNS records.
- Keep the trusted proxy ranges at the top of the Nginx template synchronized
  with Cloudflare's official [IPv4](https://www.cloudflare.com/ips-v4/) and
  [IPv6](https://www.cloudflare.com/ips-v6/) lists. Nginx rewrites the client
  address only for those source networks, preventing direct callers from
  spoofing `CF-Connecting-IP`.
- Add a Cache Rule only for `media.<domain>/media/*`: eligible for cache, Edge
  TTL 30 days, Browser TTL respects the origin. The origin sends one-year
  immutable browser caching because every new upload has a new UUID filename.
- Add a bypass rule for `api.<domain>/*`. In particular, never cache
  `/_protected-media/*`; Nginx marks that location `internal` and Django sends
  `private, no-store` on authorized responses.

Confirm a repeated public-media request returns `CF-Cache-Status: HIT` and that
direct access to `https://api.<domain>/_protected-media/...` returns 404.

## Consumer cutover

The admin dashboard and both Flutter applications connect to this deployment
through `https://api.<domain>`; they never connect to PostgreSQL, Redis, or the
Docker network. Protected media requests must include the Bearer access token.
The API never returns a private filesystem path.

Public catalog URLs are stable UUID paths. Remove Cloudinary URL rewriting in
each consumer. Keep `media.<domain>` in the admin dashboard's Next Image remote
patterns. The two Flutter apps should share a
90-day, 1000-object disk cache; the Home app must not rely on `Image.network`'s
memory-only cache.

## Monitoring and rollback

Run `deploy/check-storage.sh` from monitoring or cron. It reports disk and inode
usage at 70%, 80%, and 90%; warning/critical states use non-zero exit codes.
Also monitor `/readyz/`, container health, PostgreSQL, both Redis instances,
Celery worker/beat, and the size of `/srv/yalla/media`.

Before an important release, create a database backup; add `--with-media` for a
full local media archive:

```bash
./deploy/backup.sh
./deploy/backup.sh --with-media
```

Backups are stored under `/srv/yalla/backups` with checksums and the deployed
Git revision. A backup on the same VPS is not disaster recovery, so retain
Hostinger snapshots or copy backups to separate storage.

After pushing a tested change to the GitHub `main` branch, update production
with one command:

```bash
cd /opt/yalla_backend
./deploy/production-update.sh
```

The update script refuses a dirty checkout or a branch other than `main`, takes
a PostgreSQL backup when the database is already running, performs a
fast-forward-only Git update, and waits for the new stack to become healthy.
Useful diagnostics are:

```bash
docker compose --env-file .env.production ps
docker compose --env-file .env.production logs --tail=200 django nginx celery-worker
```

For rollback, restore the previous backend image tag and run
`docker compose --env-file .env.production up -d`. Do not replace or remove
`/srv/yalla` volumes. If a schema rollback is unsafe, restore the pre-cutover
Hostinger snapshot instead.
