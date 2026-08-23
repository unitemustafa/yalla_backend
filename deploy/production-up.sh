#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
env_file="${1:-$project_dir/.env.production}"
wait_timeout="${DEPLOY_WAIT_TIMEOUT:-300}"

if [ ! -f "$env_file" ]; then
    echo "Missing production environment file: $env_file" >&2
    echo "Copy .env.production.example to .env.production and replace every placeholder." >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not installed or is not available in PATH." >&2
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "The Docker Compose plugin is not available." >&2
    exit 1
fi

cd "$project_dir"

if command -v git >/dev/null 2>&1; then
    deployment_revision="$(git rev-parse --short=12 HEAD 2>/dev/null || true)"
fi
deployment_revision="${deployment_revision:-unknown}"

export BACKEND_ENV_FILE="$env_file"
export DEPLOYMENT_REVISION="${DEPLOYMENT_REVISION:-$deployment_revision}"

docker compose --env-file "$env_file" config --quiet
docker compose --env-file "$env_file" build
docker compose --env-file "$env_file" up \
    -d \
    --remove-orphans \
    --wait \
    --wait-timeout "$wait_timeout"
docker compose --env-file "$env_file" ps

echo "Deployment revision: $DEPLOYMENT_REVISION"
