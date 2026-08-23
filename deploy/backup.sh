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
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="$backup_root/$timestamp"
mkdir -p "$backup_root"
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
)

echo "Backup created: $backup_dir"
