#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
env_file="${1:-$project_dir/.env.production}"

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

BACKEND_ENV_FILE="$env_file" docker compose --env-file "$env_file" config --quiet
BACKEND_ENV_FILE="$env_file" docker compose --env-file "$env_file" up -d --build --remove-orphans
BACKEND_ENV_FILE="$env_file" docker compose --env-file "$env_file" ps
