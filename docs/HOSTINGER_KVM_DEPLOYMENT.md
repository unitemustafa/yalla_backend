# Hostinger KVM deployment

This deployment runs the backend API independently. The admin dashboard and
mobile applications are API consumers and are not part of this Compose stack.
PostgreSQL, both Redis instances, public media, private order media, and static
files stay outside the checkout, so rebuilding the backend image does not
remove persistent data.

## Host preparation

1. Install Docker Engine and the Compose plugin on the VPS.
2. Create the persistent paths and give the application container ownership of
   the paths it writes:

   ```bash
   sudo mkdir -p \
     /srv/yalla/media/public \
     /srv/yalla/media/private \
     /srv/yalla/static \
     /srv/yalla/postgres \
     /srv/yalla/redis/core \
     /srv/yalla/redis/cache \
     /srv/yalla/tls
   sudo chown -R 10001:10001 \
     /srv/yalla/media/public \
     /srv/yalla/media/private \
     /srv/yalla/static
   ```

   Compose initializes the backend-owned directories. PostgreSQL and Redis use
   their official image entrypoints to initialize their own data directories.

3. Copy `.env.production.example` to `.env.production`, replace every
   placeholder, and install a Cloudflare Origin CA certificate as
   `/srv/yalla/tls/origin.pem` and `/srv/yalla/tls/origin.key`.
   If `172.30.0.0/24` conflicts with a host network, change both the Compose
   subnet and `RATE_LIMIT_TRUSTED_PROXY_CIDRS` to the same private subnet.
4. Allow inbound TCP 80 and 443 only. Do not publish PostgreSQL or Redis ports.

## First cutover

1. Enable Hostinger daily backups and take a manual snapshot.
2. Back up the database and both media directories before changing DNS.
3. Run `docker compose --env-file .env.production config` and inspect the
   resolved configuration without sharing its secret-bearing output.
4. Run `./deploy/production-up.sh`. The release container runs migrations and
   collects static files successfully before the API and workers start.
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

For rollback, restore the previous backend image tag and run
`docker compose --env-file .env.production up -d`. Do not replace or remove
`/srv/yalla` volumes. If a schema rollback is unsafe, restore the pre-cutover
Hostinger snapshot instead.
