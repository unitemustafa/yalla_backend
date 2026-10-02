#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this script as root: sudo sh deploy/install-monitoring.sh" >&2
    exit 1
fi
project_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if [ "$project_dir" != /opt/yalla_backend ]; then
    echo "Systemd templates require the deployed checkout at /opt/yalla_backend." >&2
    exit 1
fi
command -v python3 >/dev/null 2>&1
python3 -c 'import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); from deploy.monitor import read_config; read_config(Path(sys.argv[1]) / ".env.production")' "$project_dir"
install -m 0644 "$project_dir/deploy/systemd/yalla-monitor.service" /etc/systemd/system/yalla-monitor.service
install -m 0644 "$project_dir/deploy/systemd/yalla-monitor.timer" /etc/systemd/system/yalla-monitor.timer
install -d -m 0755 /etc/systemd/system/yalla-backup.service.d
install -m 0644 "$project_dir/deploy/systemd/yalla-backup-monitor.conf" /etc/systemd/system/yalla-backup.service.d/monitor.conf
systemctl daemon-reload
systemctl enable --now yalla-monitor.timer
systemctl start yalla-monitor.service
systemctl status yalla-monitor.timer --no-pager
