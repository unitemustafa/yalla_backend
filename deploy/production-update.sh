#!/bin/sh
set -eu

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
env_file="${1:-$project_dir/.env.production}"
deploy_branch="${DEPLOY_BRANCH:-main}"

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

if docker compose --env-file "$env_file" ps --status running --services \
    | grep -q '^postgres$'; then
    "$project_dir/deploy/backup.sh" "$env_file"
fi

git fetch --prune origin "$deploy_branch"
git merge --ff-only "origin/$deploy_branch"

if ! "$project_dir/deploy/production-up.sh" "$env_file"; then
    echo "Deployment failed. Previous Git revision: $old_revision" >&2
    echo "Do not roll back migrations automatically; inspect container logs first." >&2
    exit 1
fi

echo "Updated $old_revision -> $(git rev-parse --short=12 HEAD)"
