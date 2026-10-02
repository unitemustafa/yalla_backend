# Host service and backup monitoring

The lightweight host monitor runs every five minutes, with no new Python packages. It probes the public `https://api.DOMAIN/readyz/` endpoint using a Dart user agent and requires JSON confirming both PostgreSQL and Redis. It also checks all persistent Compose services, their Docker health where configured, and each Celery worker's own node response. A different worker answering a broadcast ping cannot hide a stopped mail worker.

Backups must contain the completion marker, database dump, media archive and checksum manifest produced by `deploy/backup.sh --with-media`. The most recent complete local backup must be less than 30 hours old. If `YALLA_BACKUP_RCLONE_REMOTE` is set, a recent `.last-offsite-success` is also required. The monitor trusts the backup script's completion/upload verification markers; it does not reread large backup archives every five minutes. Run restore drills separately using `deploy/verify-backup.sh`. A failed systemd backup run triggers the monitor immediately through `OnFailure` and remains a failure until a backup job succeeds.

Set the explicitly authorized recipient in the host's `.env.production` before installing:

```dotenv
MONITOR_ALERT_EMAIL=yallamarket2026@gmail.com
```

The installer and test mode reject missing or invalid recipients; the setting accepts one mailbox, not a recipient list. Alerts use the SMTP settings already present inside a running backend container. SMTP credentials are not copied to the host monitor or included in its state, command line or logs. The monitor can use a running worker container if the Django container has stopped. Identical problems send one alert, then a daily reminder. Changed problems send a new alert, and full recovery sends one recovery email. Failed SMTP delivery does not advance alert state, so the next run retries. State is kept under `YALLA_DATA_ROOT/monitoring` with private permissions. It never labels an unavailable check as successful.

Install after a successful deployment and an initial complete backup from the checkout at `/opt/yalla_backend`:

```sh
cd /opt/yalla_backend
sudo sh deploy/install-monitoring.sh
```

The installer activates `yalla-monitor.timer`, installs the backup failure drop-in and runs the first check. If the first check fails, the command exits nonzero while the timer remains installed and continues checking. Inspect the cause:

```sh
sudo systemctl status yalla-monitor.timer yalla-monitor.service --no-pager
sudo journalctl -u yalla-monitor.service -n 30 --no-pager
```

For the single explicitly authorized email delivery test, run once:

```sh
sudo python3 /opt/yalla_backend/deploy/monitor.py --test-email
```

Test mode sends one email and leaves alert state unchanged. It does not simulate an outage or retry SMTP delivery within that invocation. Confirm inbox receipt before calling email delivery verified.

**External uptime monitoring is still required for complete host/network outages.** A powered-off host cannot run this timer. If Docker and every backend container are unavailable, the monitor cannot use their SMTP configuration to send mail. An independent external HTTPS monitor should check `/readyz/` every few minutes, require the expected JSON, use a Dart user agent, and alert the same recipient on failure and recovery. Do not claim the host timer alone covers these cases. Keep the external monitor outside this VPS; setting it up requires access to the chosen external service.

Local deterministic tests (no network or email delivery):

```sh
python -m unittest deploy.test_monitor
```
