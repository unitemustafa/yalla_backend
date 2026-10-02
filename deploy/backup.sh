#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
env_file="$project_dir/.env.production"
env_file_set=0
include_media=0

for argument in "$@"; do
    case "$argument" in
        --with-media)
            include_media=1
            ;;
        --help|-h)
            echo "Usage: $0 [ENV_FILE] [--with-media]"
            exit 0
            ;;
        *)
            if [ "$env_file_set" -eq 1 ]; then
                echo "Only one environment file may be supplied." >&2
                exit 1
            fi
            env_file="$argument"
            env_file_set=1
            ;;
    esac
done

if [ ! -f "$env_file" ]; then
    echo "Missing production environment file: $env_file" >&2
    exit 1
fi

read_env_value() {
    key="$1"
    fallback="$2"
    value="$(sed -n "s/^${key}=//p" "$env_file" | tail -n 1)"
    printf '%s\n' "${value:-$fallback}"
}

data_root="$(read_env_value YALLA_DATA_ROOT /srv/yalla)"
backup_root="$(read_env_value YALLA_BACKUP_ROOT "$data_root/backups")"
keep_count="$(read_env_value YALLA_BACKUP_KEEP_COUNT 7)"
offsite="$(read_env_value YALLA_BACKUP_RCLONE_REMOTE '')"

case "$keep_count" in
    ''|*[!0-9]*|0|????*)
        echo "YALLA_BACKUP_KEEP_COUNT must be a positive integer." >&2
        exit 1
        ;;
esac
if [ "$keep_count" -lt 1 ] || [ "$keep_count" -gt 365 ]; then
    echo "YALLA_BACKUP_KEEP_COUNT must be between 1 and 365." >&2
    exit 1
fi

if [ -n "$offsite" ]; then
    # Require a named remote and a dedicated prefix, never a local path or
    # the remote's root. Credentials belong in root's mode-0600 rclone config.
    if ! printf '%s\n' "$offsite" | grep -Eq '^[A-Za-z0-9_-]+:[A-Za-z0-9][A-Za-z0-9/_-]*$'; then
        echo "YALLA_BACKUP_RCLONE_REMOTE must be remote:dedicated/prefix." >&2
        exit 1
    fi
    command -v rclone >/dev/null 2>&1 || {
        echo "Offsite backup is configured but rclone is unavailable." >&2
        exit 1
    }
fi

case "$data_root" in
    /*) ;;
    *)
        echo "YALLA_DATA_ROOT must be an absolute path." >&2
        exit 1
        ;;
esac

case "$backup_root" in
    /*) ;;
    *)
        echo "YALLA_BACKUP_ROOT must be an absolute path." >&2
        exit 1
        ;;
esac

cd "$project_dir"
export BACKEND_ENV_FILE="$env_file"

if ! docker compose --env-file "$env_file" ps --status running --services \
    | grep -q '^postgres$'; then
    echo "PostgreSQL is not running; no backup was created." >&2
    exit 1
fi

umask 077
mkdir -p "$backup_root"
backup_root="$(CDPATH= cd -- "$backup_root" && pwd -P)"
if [ "$backup_root" = / ] || [ "$backup_root" = "$project_dir" ]; then
    echo "Refusing to use a filesystem or project root as the backup directory." >&2
    exit 1
fi
command -v flock >/dev/null 2>&1 || {
    echo "flock is required to prevent overlapping backup/pruning runs." >&2
    exit 1
}
exec 9>"$backup_root/.backup.lock"
flock -n 9 || {
    echo "Another backup is already running." >&2
    exit 1
}
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="$backup_root/$timestamp"
mkdir "$backup_dir"

docker compose --env-file "$env_file" exec -T postgres \
    pg_dump --format=custom --username=yalla --dbname=yalla \
    > "$backup_dir/postgres.dump"

if command -v git >/dev/null 2>&1; then
    git rev-parse HEAD > "$backup_dir/revision.txt" 2>/dev/null || true
fi

if [ "$include_media" -eq 1 ]; then
    tar -C "$data_root" -czf "$backup_dir/media.tar.gz" \
        media/public media/private
fi

(
    cd "$backup_dir"
    sha256sum postgres.dump > SHA256SUMS
    if [ "$include_media" -eq 1 ]; then
        sha256sum media.tar.gz >> SHA256SUMS
    fi
    sha256sum -c SHA256SUMS >/dev/null
    printf 'yalla-backup-v1\n' > .yalla-backup
)

# A failed upload/check fails the systemd job and leaves ALL local backups.
# No deletion/sync is ever issued to the remote; configure its lifecycle
# separately, with a retention period longer than local retention.
if [ -n "$offsite" ]; then
    rclone copy "$backup_dir" "${offsite%/}/$timestamp" --quiet
    rclone check "$backup_dir" "${offsite%/}/$timestamp" --one-way --download --quiet
    printf '%s\n' "$timestamp" > "$backup_root/.last-offsite-success"
fi

# Only our complete, checksum-valid, directly-owned timestamp folders qualify.
# Legacy/unmarked, partial, corrupt and symlink folders are left for review.
candidate_list="$(mktemp "$backup_root/.prune-candidates.XXXXXX")"
trap 'rm -f -- "$candidate_list"' EXIT HUP INT TERM
: > "$candidate_list"
for candidate in "$backup_root"/*; do
    [ -d "$candidate" ] && [ ! -L "$candidate" ] || continue
    name="${candidate##*/}"
    printf '%s\n' "$name" | grep -Eq '^[0-9]{8}T[0-9]{6}Z$' || continue
    [ -f "$candidate/.yalla-backup" ] && [ ! -L "$candidate/.yalla-backup" ] || continue
    [ "$(cat "$candidate/.yalla-backup")" = yalla-backup-v1 ] || continue
    [ -f "$candidate/postgres.dump" ] && [ ! -L "$candidate/postgres.dump" ] || continue
    [ -f "$candidate/SHA256SUMS" ] && [ ! -L "$candidate/SHA256SUMS" ] || continue
    grep -Eq '^[0-9a-f]{64}  postgres.dump$' "$candidate/SHA256SUMS" || continue
    # Reject manifests containing paths outside this owned directory.
    if grep -Ev '^[0-9a-f]{64}  (postgres.dump|media.tar.gz)$' "$candidate/SHA256SUMS" >/dev/null; then
        continue
    fi
    if ! (cd "$candidate" && sha256sum -c SHA256SUMS >/dev/null 2>&1); then
        continue
    fi
    printf '%s\n' "$name" >> "$candidate_list"
done
sort -r "$candidate_list" -o "$candidate_list"
count=0
while IFS= read -r name; do
    count=$((count + 1))
    [ "$count" -gt "$keep_count" ] || continue
    candidate="$backup_root/$name"
    [ "${candidate%/*}" = "$backup_root" ] && [ ! -L "$candidate" ] || exit 1
    rm -rf -- "$candidate"
done < "$candidate_list"

echo "Backup created: $backup_dir"
