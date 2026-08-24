#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
deploy_branch="${DEPLOY_BRANCH:-main}"
env_file=""
apply_gunicorn_profile=0
profile_tmp_file=""

cleanup_profile_tmp_file() {
    if [ -n "$profile_tmp_file" ]; then
        rm -f "$profile_tmp_file"
    fi
}

trap cleanup_profile_tmp_file EXIT HUP INT TERM

for argument in "$@"; do
    case "$argument" in
        --apply-gunicorn-profile)
            apply_gunicorn_profile=1
            ;;
        --help|-h)
            echo "Usage: $0 [ENV_FILE] [--apply-gunicorn-profile]"
            exit 0
            ;;
        -*)
            echo "Unknown option: $argument" >&2
            exit 1
            ;;
        *)
            if [ -n "$env_file" ]; then
                echo "Only one environment file may be supplied." >&2
                exit 1
            fi
            env_file="$argument"
            ;;
    esac
done

env_file="${env_file:-$project_dir/.env.production}"

if [ ! -f "$env_file" ]; then
    echo "Missing production environment file: $env_file" >&2
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo "Git is not installed or is not available in PATH." >&2
    exit 1
fi

cd "$project_dir"

current_branch="$(git branch --show-current)"
if [ "$current_branch" != "$deploy_branch" ]; then
    echo "Expected branch '$deploy_branch', but '$current_branch' is checked out." >&2
    exit 1
fi

if [ -n "$(git status --short --untracked-files=no)" ]; then
    echo "Tracked files have local changes. Commit or discard them before deployment." >&2
    exit 1
fi

old_revision="$(git rev-parse --short=12 HEAD)"
export BACKEND_ENV_FILE="$env_file"
backup_dir=""
rollback_image=""
backend_image=""

if docker compose --env-file "$env_file" ps --status running --services \
    | grep -q '^postgres$'; then
    if [ "$apply_gunicorn_profile" -eq 1 ]; then
        backup_output="$(
            "$project_dir/deploy/backup.sh" "$env_file" --with-media
        )"
        printf '%s\n' "$backup_output"
        backup_dir="${backup_output##*Backup created: }"
    else
        "$project_dir/deploy/backup.sh" "$env_file"
    fi
elif [ "$apply_gunicorn_profile" -eq 1 ]; then
    echo "PostgreSQL must be healthy before applying the Gunicorn profile." >&2
    exit 1
fi

git fetch --prune origin "$deploy_branch"
git merge --ff-only "origin/$deploy_branch"

if [ "$apply_gunicorn_profile" -eq 1 ]; then
    if [ -z "$backup_dir" ] || [ ! -d "$backup_dir" ]; then
        echo "The release backup directory could not be identified." >&2
        exit 1
    fi

    install -o root -g root -m 0600 \
        "$env_file" \
        "$backup_dir/.env.production"

    backend_image="$(
        sed -n 's/^BACKEND_IMAGE=//p' "$env_file" | tail -n 1
    )"
    backend_image="${backend_image:-yalla-backend:latest}"
    rollback_image="yalla-backend:rollback-$old_revision"
    docker image inspect "$backend_image" >/dev/null
    docker image tag "$backend_image" "$rollback_image"
    printf '%s\n' "$rollback_image" > "$backup_dir/rollback-image.txt"

    profile_tmp_file="$(mktemp "$project_dir/.env.production.XXXXXX")"
    awk '
        BEGIN {
            count = 8
            keys[1] = "PORT"
            keys[2] = "WEB_CONCURRENCY"
            keys[3] = "GUNICORN_THREADS"
            keys[4] = "GUNICORN_TIMEOUT"
            keys[5] = "GUNICORN_GRACEFUL_TIMEOUT"
            keys[6] = "GUNICORN_KEEPALIVE"
            keys[7] = "GUNICORN_MAX_REQUESTS"
            keys[8] = "GUNICORN_MAX_REQUESTS_JITTER"
            values["PORT"] = "8000"
            values["WEB_CONCURRENCY"] = "4"
            values["GUNICORN_THREADS"] = "2"
            values["GUNICORN_TIMEOUT"] = "120"
            values["GUNICORN_GRACEFUL_TIMEOUT"] = "30"
            values["GUNICORN_KEEPALIVE"] = "5"
            values["GUNICORN_MAX_REQUESTS"] = "1000"
            values["GUNICORN_MAX_REQUESTS_JITTER"] = "100"
        }
        {
            key = $0
            sub(/=.*/, "", key)
            if (key in values) {
                if (!seen[key]++) {
                    print key "=" values[key]
                }
            } else {
                print
            }
        }
        END {
            for (index = 1; index <= count; index++) {
                key = keys[index]
                if (!seen[key]) {
                    print key "=" values[key]
                }
            }
        }
    ' "$env_file" > "$profile_tmp_file"
    chown --reference="$env_file" "$profile_tmp_file"
    chmod 0600 "$profile_tmp_file"
    mv "$profile_tmp_file" "$env_file"
    profile_tmp_file=""
fi

if ! "$project_dir/deploy/production-up.sh" "$env_file"; then
    echo "Deployment failed. Previous Git revision: $old_revision" >&2
    echo "Do not roll back migrations automatically; inspect container logs first." >&2

    if [ "$apply_gunicorn_profile" -eq 1 ]; then
        echo "Restoring the previous environment and application image." >&2
        install -o root -g root -m 0600 \
            "$backup_dir/.env.production" \
            "$env_file"
        docker image tag "$rollback_image" "$backend_image"
        DEPLOYMENT_REVISION="$old_revision" \
            docker compose --env-file "$env_file" up \
                -d \
                --no-build \
                --force-recreate \
                --wait \
                --wait-timeout 300 \
                django nginx
        echo "Application rollback completed without reversing migrations." >&2
    fi

    exit 1
fi

echo "Updated $old_revision -> $(git rev-parse --short=12 HEAD)"
