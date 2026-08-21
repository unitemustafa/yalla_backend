#!/bin/sh
set -eu

check_mount() {
    target="$1"
    label="$2"
    disk_percent="$(df -P "$target" | awk 'NR == 2 {gsub("%", "", $5); print $5}')"
    inode_percent="$(df -Pi "$target" | awk 'NR == 2 {gsub("%", "", $5); print $5}')"
    level="OK"
    code=0
    if [ "$disk_percent" -ge 90 ] || [ "$inode_percent" -ge 90 ]; then
        level="CRITICAL"
        code=2
    elif [ "$disk_percent" -ge 80 ] || [ "$inode_percent" -ge 80 ]; then
        level="WARNING"
        code=1
    elif [ "$disk_percent" -ge 70 ] || [ "$inode_percent" -ge 70 ]; then
        level="NOTICE"
    fi
    echo "$level $label disk=${disk_percent}% inodes=${inode_percent}%"
    return "$code"
}

exit_code=0
status=0
check_mount /srv/yalla/media/public public-media || status="$?"
if [ "$status" -gt "$exit_code" ]; then
    exit_code="$status"
fi
status=0
check_mount /srv/yalla/media/private private-media || status="$?"
if [ "$status" -gt "$exit_code" ]; then
    exit_code="$status"
fi
du -sh /srv/yalla/media/public /srv/yalla/media/private
exit "$exit_code"
