#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this script as root: sudo ./deploy/install-systemd-units.sh" >&2
    exit 1
fi

project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

install -m 0644 \
    "$project_dir/deploy/systemd/yalla-backup.service" \
    /etc/systemd/system/yalla-backup.service
install -m 0644 \
    "$project_dir/deploy/systemd/yalla-backup.timer" \
    /etc/systemd/system/yalla-backup.timer
install -m 0644 \
    "$project_dir/deploy/systemd/yalla-auth-cleanup.service" \
    /etc/systemd/system/yalla-auth-cleanup.service
install -m 0644 \
    "$project_dir/deploy/systemd/yalla-auth-cleanup.timer" \
    /etc/systemd/system/yalla-auth-cleanup.timer

systemctl daemon-reload
systemctl enable --now yalla-backup.timer
systemctl enable --now yalla-auth-cleanup.timer
systemctl status yalla-backup.timer --no-pager
systemctl status yalla-auth-cleanup.timer --no-pager
