#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this script as root: sudo ./deploy/hostinger-bootstrap.sh" >&2
    exit 1
fi

if [ ! -r /etc/os-release ]; then
    echo "Cannot identify this operating system." >&2
    exit 1
fi

# shellcheck disable=SC1091
. /etc/os-release

if [ "${ID:-}" != "ubuntu" ]; then
    echo "This bootstrap script supports Ubuntu only." >&2
    exit 1
fi

install_docker=1
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    install_docker=0
fi

if [ "$install_docker" -eq 1 ]; then
    conflicts=""
    for package in \
        docker.io \
        docker-compose \
        docker-compose-v2 \
        docker-doc \
        podman-docker \
        containerd \
        runc; do
        if dpkg-query -W -f='${db:Status-Status}' "$package" 2>/dev/null \
            | grep -q '^installed$'; then
            conflicts="$conflicts $package"
        fi
    done

    if [ -n "$conflicts" ]; then
        echo "Conflicting Docker packages are installed:$conflicts" >&2
        echo "Review and remove them before installing Docker Engine from Docker's repository." >&2
        exit 1
    fi

    apt-get update
    apt-get install -y ca-certificates curl git
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    architecture="$(dpkg --print-architecture)"
    codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
    if [ -z "$codename" ]; then
        echo "Cannot determine the Ubuntu release codename." >&2
        exit 1
    fi

    printf '%s\n' \
        "deb [arch=$architecture signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $codename stable" \
        > /etc/apt/sources.list.d/docker.list

    apt-get update
    apt-get install -y \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin
fi

systemctl enable --now docker

install -d -m 0755 \
    /srv/yalla/media/public \
    /srv/yalla/media/private \
    /srv/yalla/static \
    /srv/yalla/postgres \
    /srv/yalla/tls
install -d -m 0700 /srv/yalla/backups

chown -R 10001:10001 \
    /srv/yalla/media/public \
    /srv/yalla/media/private \
    /srv/yalla/static

docker --version
docker compose version

echo "Host preparation is complete."
echo "Next: create .env.production and install the Cloudflare Origin CA files."
