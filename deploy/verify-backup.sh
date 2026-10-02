#!/bin/sh
set -eu

if [ "$#" -ne 1 ] || [ ! -d "$1" ]; then
    echo "Usage: $0 /absolute/path/to/backup-folder" >&2
    exit 1
fi
backup_dir="$(CDPATH= cd -- "$1" && pwd -P)"
if [ ! -f "$backup_dir/postgres.dump" ] || [ ! -f "$backup_dir/SHA256SUMS" ]; then
    echo "Backup dump or checksum manifest is missing." >&2
    exit 1
fi
if grep -Ev '^[0-9a-f]{64}  (postgres.dump|media.tar.gz)$' "$backup_dir/SHA256SUMS" >/dev/null; then
    echo "Invalid backup checksum manifest." >&2
    exit 1
fi
if ! grep -Eq '^[0-9a-f]{64}  postgres.dump$' "$backup_dir/SHA256SUMS"; then
    echo "The database dump checksum is missing." >&2
    exit 1
fi
(cd "$backup_dir" && sha256sum -c SHA256SUMS)

# This is a fresh isolated container, with no network, published ports, or
# production volume. No application settings, source DB, or .env are loaded.
container="yalla-restore-verify-$(date -u +%Y%m%dT%H%M%SZ)-$$"
cleanup() {
    docker rm -f "$container" >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM
docker run --detach --rm --name "$container" --network none \
    -e POSTGRES_DB=yalla_restore -e POSTGRES_USER=yalla_restore \
    -e POSTGRES_HOST_AUTH_METHOD=trust postgres:17-alpine >/dev/null
# Copy only the verified dump; the host's backup/production directories are
# never mounted into the restore container (also works with a remote daemon).
docker cp "$backup_dir/postgres.dump" "$container:/tmp/yalla-verify.dump"
attempt=0
until docker exec "$container" pg_isready -U yalla_restore -d yalla_restore >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    [ "$attempt" -lt 30 ] || {
        echo "Isolated PostgreSQL did not become ready." >&2
        exit 1
    }
    sleep 1
done
docker exec "$container" pg_restore --exit-on-error --no-owner --no-privileges \
    --username=yalla_restore --dbname=yalla_restore /tmp/yalla-verify.dump
docker exec "$container" psql --username=yalla_restore --dbname=yalla_restore \
    --no-psqlrc --set=ON_ERROR_STOP=1 --tuples-only \
    --command="SELECT 'public tables restored: ' || count(*) FROM information_schema.tables WHERE table_schema = 'public';"
echo "Isolated PostgreSQL restore succeeded."
