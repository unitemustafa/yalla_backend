# Release operations for the initial audience

The current PostgreSQL/Redis/Gunicorn/Celery stack is sufficient to start with
the expected audience. Keep this checklist alongside the deployed revision.
Run these commands on the VPS host in `/opt/yalla_backend`, after reviewing
and publishing the tested changes. They do not substitute for release checks
on Android and iPhone.

## Backups and recovery

`deploy/backup.sh --with-media` creates a custom PostgreSQL dump, local media
archive, checksums and revision. Only after every local file is complete does
it create its ownership marker. `flock` prevents overlapping timer/release
backups. `YALLA_BACKUP_KEEP_COUNT` defaults to seven complete backups. It leaves
unmarked legacy folders, incomplete/corrupt backups and symlinks untouched;
review old pre-policy backups manually after verifying an external copy.

For external storage, install rclone on the VPS and configure a named remote
as the backup service user (the supplied service runs as root). Store its
credentials in that user's mode-0600 rclone configuration, and set only a
destination such as `YALLA_BACKUP_RCLONE_REMOTE=backups:yalla-production` in
`.env.production`. Use a dedicated private bucket/prefix. The job copies,
verifies the remote by downloading its contents, and only then prunes local
backups. Upload or verification failure fails the job and retains every local
backup. This verification uses bandwidth equal to the archive size; account
for it in the storage plan. The script never deletes remote data. Configure
the remote lifecycle separately, for example 30 days, and verify the first
expiry before relying on it. A destination left empty means local backups
only; it is not external disaster recovery.

Verify installation and a first backup:

```sh
sudo ./deploy/install-systemd-units.sh
sudo systemctl start yalla-backup.service
sudo systemctl status yalla-backup.service --no-pager
sudo journalctl -u yalla-backup.service --since '2 days ago' --no-pager
sudo systemctl list-timers yalla-backup.timer
```

Retrieve a chosen external backup into a separate scratch folder, then:

```sh
sh ./deploy/verify-backup.sh /absolute/path/to/retrieved/backup
```

The verifier checks the manifest and restores to a disposable PostgreSQL 17
container with no network, exposed ports or production volumes. It never
loads `.env.production` and removes the container on exit. It does not restore
over production. Keep the manifest, deployed revision, table/row counts and
test date as recovery evidence. A successful database restore verifies the
dump, not the correctness of every business record or media reference; compare
order/user/event counts and inspect the media archive in the isolated recovery
environment. Local media archives apply to filesystem storage. If media is
stored in R2/S3, enable the bucket's versioning/retention and recovery procedure
as well; a local tar is not a backup of remote objects.

Daily backups can lose up to a day of orders. Decide an acceptable recovery
point and shorten the timer if needed; full media archives should be scheduled
according to actual storage growth.

## Minimal monitoring

Configure an external uptime service to alert the operator when `/readyz/`
fails twice consecutively. Initial thresholds to tune after launch: sustained
5xx above 1%, p95 above 2 seconds, disk/inodes above 80%, or no successful
daily backup for 26 hours. Monitor 429 by endpoint before adjusting rate
limits. Use the existing request IDs to investigate, without logging tokens,
OTP values or private customer details.

Check workers, not just the web process:

```sh
docker compose --env-file .env.production ps
docker compose --env-file .env.production exec -T celery-worker celery -A config inspect ping --timeout 5
docker compose --env-file .env.production logs --since 10m --tail 100 celery-worker celery-media-worker celery-beat
./deploy/check-storage.sh
```

Redis/PostgreSQL must remain private, with no published host ports. Verify
Cloudflare Full (Strict), API/private-media cache bypass, SSH key access and
the firewall in the actual accounts. Public `/healthz/` cannot prove these.

## Release evidence

Record backend/admin revisions, mobile version/build numbers, signed artifact
hashes, symbols/mapping files, and successful test/restore logs. Apply the
backend migration/contract changes before distributing dependent mobile/admin
releases. Take the pre-release backup, review migration SQL, keep the previous
image, and run the documented `production-update.sh` entry point.

Use dedicated test accounts for one complete order journey, including selected
additions, retry after a lost response, assignment, delivery proof, allowed
cancellation and logout. Verify notification taps in foreground/background/
terminated states and account switching on both Android and iOS. iOS signing,
Firebase/APNs and TestFlight require the real Apple/Firebase account settings
and a Mac; their values cannot be inferred from this repository.
