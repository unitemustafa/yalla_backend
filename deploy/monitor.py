#!/usr/bin/env python3
"""Small host monitor. SMTP credentials stay inside the backend container."""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request


SERVICES = (
    "nginx", "django", "postgres", "redis", "celery-worker",
    "celery-media-worker", "celery-beat",
)
BACKEND_SERVICES = ("django", "celery-worker", "celery-media-worker")
BACKUP_MAX_AGE = 30 * 60 * 60
REMINDER_INTERVAL = 24 * 60 * 60
CONFIG_KEYS = {"DOMAIN", "YALLA_DATA_ROOT", "YALLA_BACKUP_ROOT", "YALLA_BACKUP_RCLONE_REMOTE", "MONITOR_ALERT_EMAIL"}


def validate_recipient(value):
    if (
        not isinstance(value, str) or len(value) > 254 or "\r" in value or "\n" in value
        or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}", value)
    ):
        raise ValueError("MONITOR_ALERT_EMAIL must be one email address")
    return value


def read_config(path):
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.strip().partition("=")
        if separator and key in CONFIG_KEYS:
            values[key] = value.strip().strip("\"'")
    domain = values.get("DOMAIN", "")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", domain) or "." not in domain:
        raise ValueError("DOMAIN must be a domain name")
    data_root = Path(values.get("YALLA_DATA_ROOT", "/srv/yalla"))
    backup_root = Path(values.get("YALLA_BACKUP_ROOT", str(data_root / "backups")))
    if not data_root.is_absolute() or not backup_root.is_absolute():
        raise ValueError("Data and backup directories must be absolute")
    recipient = validate_recipient(values.get("MONITOR_ALERT_EMAIL", ""))
    return domain, data_root, backup_root, bool(values.get("YALLA_BACKUP_RCLONE_REMOTE")), recipient


def command(args, *, cwd, input_text=None, timeout=25):
    return subprocess.run(
        args, cwd=cwd, input=input_text, text=True, capture_output=True,
        timeout=timeout, check=True,
    ).stdout


def compose_args(env_file):
    return ["docker", "compose", "--env-file", str(env_file)]


def parse_services(output):
    # Compose versions emit either one JSON array or one object per line.
    try:
        records = json.loads(output)
        if isinstance(records, dict):
            records = [records]
    except json.JSONDecodeError:
        records = [json.loads(line) for line in output.splitlines() if line.strip()]
    if not isinstance(records, list):
        raise ValueError("Unexpected Docker Compose status response")
    return {record["Service"]: record for record in records}


def service_issues(records):
    issues = {}
    for service in SERVICES:
        record = records.get(service)
        if record is None or record.get("State") != "running":
            issues[f"service:{service}"] = f"{service}: container is not running"
        elif service != "celery-beat" and record.get("Health") != "healthy":
            issues[f"service:{service}"] = f"{service}: container health is not healthy"
    return issues


def probe_readiness(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": "Dart/3.9 (dart:io)", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.geturl() != url or response.status != 200:
            raise ValueError("Readiness request redirected or returned non-200")
        payload = json.loads(response.read(4097))
    checks = payload.get("checks")
    if (
        payload.get("status") != "ok" or not isinstance(checks, dict)
        or checks.get("database") is not True or checks.get("redis") is not True
    ):
        raise ValueError("Readiness response did not confirm database and Redis")


def backup_timestamp(value):
    return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp()


def fresh_timestamp(value, now):
    try:
        age = now - backup_timestamp(value)
    except ValueError:
        return False
    return -300 <= age <= BACKUP_MAX_AGE


def backup_issues(root, offsite_required, now):
    issues = {}
    complete = []
    if root.is_dir():
        for folder in root.iterdir():
            if folder.is_symlink() or not folder.is_dir():
                continue
            if not re.fullmatch(r"\d{8}T\d{6}Z", folder.name):
                continue
            marker = folder / ".yalla-backup"
            files = [marker, folder / "postgres.dump", folder / "media.tar.gz", folder / "SHA256SUMS"]
            if any(path.is_symlink() or not path.is_file() or path.stat().st_size == 0 for path in files):
                continue
            if marker.read_text(encoding="utf-8").strip() == "yalla-backup-v1":
                complete.append(folder.name)
    if not complete or not fresh_timestamp(max(complete), now):
        issues["backup:local"] = "No completed PostgreSQL + media backup within the last 30 hours"
    if offsite_required:
        marker = root / ".last-offsite-success"
        value = marker.read_text(encoding="utf-8").strip() if marker.is_file() and not marker.is_symlink() else ""
        if not fresh_timestamp(value, now):
            issues["backup:offsite"] = "No verified offsite backup upload within the last 30 hours"
    return issues


def collect_issues(project_dir, env_file, domain, backup_root, offsite_required, now):
    issues = {}
    records = {}
    try:
        probe_readiness(f"https://api.{domain}/readyz/")
    except Exception:
        issues["readiness"] = "Public readiness probe failed (HTTP, TLS, DNS, timeout, or dependency check)"
    try:
        records = parse_services(command(
            compose_args(env_file) + ["ps", "--all", "--format", "json"], cwd=project_dir,
        ))
        issues.update(service_issues(records))
    except Exception:
        issues["docker"] = "Could not inspect Docker Compose services"
    for service, node_prefix in (("celery-worker", "celery"), ("celery-media-worker", "media")):
        if records.get(service, {}).get("State") != "running":
            continue
        code = (
            "import socket, sys; from config.celery import app; "
            f"node={node_prefix!r}+'@'+socket.gethostname(); "
            "reply=app.control.inspect(destination=[node], timeout=5).ping(); "
            "sys.exit(0 if reply and reply.get(node, {}).get('ok') == 'pong' else 1)"
        )
        try:
            command(compose_args(env_file) + ["exec", "-T", service, "python", "-c", code], cwd=project_dir, timeout=15)
        except Exception:
            issues[f"celery:{service}"] = f"{service}: its own Celery node did not answer ping"
    try:
        issues.update(backup_issues(backup_root, offsite_required, now))
        result = command(
            ["systemctl", "show", "yalla-backup.service", "--property=Result", "--value"],
            cwd=project_dir, timeout=5,
        ).strip()
        if result != "success":
            issues["backup:job"] = "Most recent systemd backup job failed or its status is unavailable"
    except Exception:
        issues["backup:inspection"] = "Could not inspect backup freshness or job status"
    return issues, records


def send_email(project_dir, env_file, records, recipient, subject, body):
    validate_recipient(recipient)
    service = next((name for name in BACKEND_SERVICES if records.get(name, {}).get("State") == "running"), None)
    if service is None:
        raise RuntimeError("No running backend container can send the alert")
    # Payload goes over stdin; neither the command line nor logs contain SMTP credentials.
    code = (
        "import json, os, sys; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); "
        "import django; django.setup(); from django.conf import settings; "
        "from django.core.mail import send_mail; settings.EMAIL_TIMEOUT=10; "
        "p=json.load(sys.stdin); "
        "sys.exit(0 if send_mail(p['subject'], p['body'], settings.DEFAULT_FROM_EMAIL, "
        "[p['recipient']], fail_silently=False) == 1 else 1)"
    )
    command(
        compose_args(env_file) + ["exec", "-T", service, "python", "-c", code],
        cwd=project_dir,
        input_text=json.dumps({"subject": subject, "body": body, "recipient": recipient}),
        timeout=25,
    )


def alert_action(state, issues, now):
    previous = state.get("issues", {})
    if issues:
        if issues != previous or now - state.get("last_sent_at", 0) >= REMINDER_INTERVAL:
            return "failure"
    elif previous:
        return "recovery"
    return None


def update_alert_state(state_path, issues, now, send):
    state = {}
    state_invalid = False
    try:
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if not isinstance(state, dict) or not isinstance(state.get("issues", {}), dict):
                raise ValueError("Invalid monitor state")
            timestamp = state.get("last_sent_at", 0)
            if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp):
                raise ValueError("Invalid monitor state timestamp")
    except (OSError, ValueError, OverflowError):
        state_invalid = True
        state = {}
    if state_invalid:
        issues["monitor:state"] = "Monitor alert state could not be read; alert deduplication was reset"
    action = alert_action(state, issues, now)
    if action:
        subject = "[Yalla] Service or backup problem" if action == "failure" else "[Yalla] Service and backup checks recovered"
        body = "\n".join(sorted(issues.values())) if issues else "All monitored service and backup checks now pass."
        send(subject, body)
        # Failed SMTP never advances state; the next timer run retries the alert.
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"issues": issues, "last_sent_at": now}), encoding="utf-8")
        temporary.replace(state_path)
    return action


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--test-email", action="store_true", help="Send exactly one test email; do not change alert state")
    args = parser.parse_args()
    project_dir = Path(__file__).resolve().parent.parent
    env_file = (args.env_file or project_dir / ".env.production").resolve()
    os.environ["BACKEND_ENV_FILE"] = str(env_file)
    try:
        domain, data_root, backup_root, offsite, recipient = read_config(env_file)
        if args.test_email:
            records = parse_services(command(compose_args(env_file) + ["ps", "--all", "--format", "json"], cwd=project_dir))
            send_email(project_dir, env_file, records, recipient, "[Yalla] Monitoring test", "The Yalla host monitor can deliver email alerts. This is the requested single test email.")
            print("Monitoring test email sent")
            return 0
        import fcntl
        state_dir = data_root / "monitoring"
        state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.umask(0o077)
        with (state_dir / "monitor.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("Another monitor run is in progress")
                return 0
            now = time.time()
            issues, records = collect_issues(project_dir, env_file, domain, backup_root, offsite, now)
            if issues:
                print("Monitor checks failed: " + ", ".join(sorted(issues)), flush=True)
            update_alert_state(
                state_dir / "alerts.json", issues, now,
                lambda subject, body: send_email(project_dir, env_file, records, recipient, subject, body),
            )
            if issues:
                return 1
            print("All monitored checks pass")
            return 0
    except Exception as exc:
        # Do not print exception text: subprocess/SMTP errors may contain sensitive values.
        print(f"Monitor failed ({type(exc).__name__}); inspect the host and SMTP configuration", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
