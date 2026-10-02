import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from deploy import monitor


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.now = monitor.backup_timestamp("20261003T120000Z")

    def complete_backup(self, timestamp="20261003T110000Z"):
        folder = self.root / timestamp
        folder.mkdir()
        (folder / ".yalla-backup").write_text("yalla-backup-v1\n", encoding="utf-8")
        for name in ("postgres.dump", "media.tar.gz", "SHA256SUMS"):
            (folder / name).write_text("complete", encoding="utf-8")
        return folder

    def healthy_services(self):
        return {name: {"Service": name, "State": "running", "Health": "healthy"} for name in monitor.SERVICES}

    def test_compose_array_and_json_lines_have_same_status(self):
        records = list(self.healthy_services().values())
        self.assertEqual(
            monitor.parse_services(json.dumps(records)),
            monitor.parse_services("\n".join(json.dumps(record) for record in records)),
        )

    def test_missing_stopped_and_missing_health_are_failures(self):
        records = self.healthy_services()
        del records["postgres"]
        records["redis"]["State"] = "exited"
        records["celery-worker"]["Health"] = ""
        records["celery-beat"]["Health"] = ""
        self.assertEqual(set(monitor.service_issues(records)), {"service:postgres", "service:redis", "service:celery-worker"})

    @patch("deploy.monitor.urllib.request.urlopen")
    def test_readiness_requires_real_dependency_success_with_dart_user_agent(self, open_url):
        response = open_url.return_value.__enter__.return_value
        url = "https://api.example.com/readyz/"
        response.geturl.return_value = url
        response.status = 200
        response.read.return_value = b'{"status":"ok","checks":{"database":true,"redis":true}}'
        monitor.probe_readiness(url)
        request = open_url.call_args.args[0]
        self.assertTrue(request.get_header("User-agent").startswith("Dart/"))
        response.read.return_value = b'{"status":"ok","checks":{"database":true,"redis":false}}'
        with self.assertRaises(ValueError):
            monitor.probe_readiness(url)
        response.read.return_value = b'<html>Cloudflare challenge</html>'
        with self.assertRaises(ValueError):
            monitor.probe_readiness(url)

    def test_complete_backup_passes_but_partial_media_does_not(self):
        folder = self.complete_backup()
        self.assertEqual(monitor.backup_issues(self.root, False, self.now), {})
        (folder / "media.tar.gz").unlink()
        self.assertIn("backup:local", monitor.backup_issues(self.root, False, self.now))

    def test_stale_future_and_unmarked_backups_do_not_pass(self):
        self.complete_backup("20261001T110000Z")
        self.complete_backup("20261004T110000Z")
        unmarked = self.complete_backup()
        (unmarked / ".yalla-backup").unlink()
        self.assertIn("backup:local", monitor.backup_issues(self.root, False, self.now))

    def test_offsite_is_independently_checked_after_local_success(self):
        self.complete_backup()
        self.assertEqual(set(monitor.backup_issues(self.root, True, self.now)), {"backup:offsite"})
        marker = self.root / ".last-offsite-success"
        marker.write_text("20261003T110000Z\n", encoding="utf-8")
        self.assertEqual(monitor.backup_issues(self.root, True, self.now), {})
        marker.write_text("20261001T110000Z", encoding="utf-8")
        self.assertIn("backup:offsite", monitor.backup_issues(self.root, True, self.now))

    def test_failure_dedup_changed_problem_daily_reminder_and_recovery(self):
        path = self.root / "alerts.json"
        send = Mock()
        issue = {"readiness": "probe failed"}
        self.assertEqual(monitor.update_alert_state(path, issue.copy(), self.now, send), "failure")
        self.assertIsNone(monitor.update_alert_state(path, issue.copy(), self.now + 300, send))
        self.assertEqual(monitor.update_alert_state(path, issue.copy(), self.now + 86400, send), "failure")
        changed = {**issue, "backup:local": "backup stale"}
        self.assertEqual(monitor.update_alert_state(path, changed, self.now + 86700, send), "failure")
        self.assertEqual(monitor.update_alert_state(path, {}, self.now + 87000, send), "recovery")
        self.assertIsNone(monitor.update_alert_state(path, {}, self.now + 87300, send))
        self.assertEqual(send.call_count, 4)

    def test_failed_email_does_not_mark_the_alert_sent(self):
        path = self.root / "alerts.json"
        send = Mock(side_effect=RuntimeError("SMTP down"))
        with self.assertRaises(RuntimeError):
            monitor.update_alert_state(path, {"readiness": "failed"}, self.now, send)
        self.assertFalse(path.exists())
        send.side_effect = None
        self.assertEqual(monitor.update_alert_state(path, {"readiness": "failed"}, self.now + 300, send), "failure")

    def test_corrupt_state_creates_a_failure_not_a_false_recovery(self):
        path = self.root / "alerts.json"
        path.write_text("broken", encoding="utf-8")
        send = Mock()
        issues = {}
        self.assertEqual(monitor.update_alert_state(path, issues, self.now, send), "failure")
        self.assertIn("monitor:state", issues)
        self.assertIn("problem", send.call_args.args[0])

    def test_invalid_state_timestamps_cannot_disable_alerts(self):
        path = self.root / "alerts.json"
        for invalid in ("yesterday", float("nan"), float("inf"), True, None):
            with self.subTest(timestamp=invalid):
                path.write_text(json.dumps({"issues": {"readiness": "failed"}, "last_sent_at": invalid}), encoding="utf-8")
                send = Mock()
                issues = {"readiness": "failed"}
                self.assertEqual(monitor.update_alert_state(path, issues, self.now, send), "failure")
                send.assert_called_once()
                self.assertIn("monitor:state", issues)
                self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["last_sent_at"], self.now)

    def test_recipient_requires_a_single_mailbox_without_header_injection(self):
        self.assertEqual(monitor.validate_recipient("alerts@example.com"), "alerts@example.com")
        for invalid in ("", "a@example.com,b@example.com", "Owner <a@example.com>", "a@example.com\r\nBcc: b@example.com", "a@example.com\n", "a@example.com ", "a@localhost"):
            with self.subTest(recipient=invalid), self.assertRaises(ValueError):
                monitor.validate_recipient(invalid)

    def test_config_requires_alert_recipient_before_install_or_email_test(self):
        config = self.root / ".env"
        base = f"DOMAIN=example.com\nYALLA_DATA_ROOT={self.root}\n"
        config.write_text(base, encoding="utf-8")
        with self.assertRaises(ValueError):
            monitor.read_config(config)
        config.write_text(base + "MONITOR_ALERT_EMAIL=alerts@example.com\n", encoding="utf-8")
        self.assertEqual(monitor.read_config(config)[-1], "alerts@example.com")

    @patch("deploy.monitor.command")
    @patch("deploy.monitor.probe_readiness")
    def test_own_celery_ping_and_failed_backup_job_are_not_hidden_by_green_docker(self, probe, run):
        self.complete_backup()
        def fake_command(args, **kwargs):
            if args[0] == "systemctl":
                return "exit-code\n"
            if "ps" in args:
                return json.dumps(list(self.healthy_services().values()))
            if "celery-worker" in args:
                raise RuntimeError("mail worker does not respond")
            return ""
        run.side_effect = fake_command
        issues, _ = monitor.collect_issues(self.root, self.root / ".env", "example.com", self.root, False, self.now)
        self.assertEqual(set(issues), {"celery:celery-worker", "backup:job"})
        calls = [call.args[0] for call in run.call_args_list if "exec" in call.args[0]]
        self.assertIn("destination=[node]", calls[0][-1])

    @patch("deploy.monitor.command")
    def test_email_uses_running_container_stdin_and_does_not_retry_delivery(self, run):
        records = {"celery-worker": {"State": "running"}}
        monitor.send_email(self.root, self.root / ".env", records, "alerts@example.com", "Alert", "Backup stale")
        self.assertEqual(run.call_count, 1)
        args = run.call_args.args[0]
        self.assertIn("celery-worker", args)
        self.assertNotIn("alerts@example.com", " ".join(args))
        payload = json.loads(run.call_args.kwargs["input_text"])
        self.assertEqual(payload["recipient"], "alerts@example.com")
        with self.assertRaises(RuntimeError):
            monitor.send_email(self.root, self.root / ".env", {}, "alerts@example.com", "Alert", "Failed")

    @patch("deploy.monitor.send_email")
    @patch("deploy.monitor.command")
    @patch("deploy.monitor.read_config")
    def test_test_email_mode_sends_once_and_does_not_modify_state(self, config, run, send):
        config.return_value = ("example.com", self.root, self.root, False, "alerts@example.com")
        run.return_value = json.dumps(list(self.healthy_services().values()))
        with patch("sys.argv", ["monitor.py", "--test-email"]), patch.dict("os.environ"):
            self.assertEqual(monitor.main(), 0)
        send.assert_called_once()
        self.assertFalse((self.root / "monitoring").exists())


if __name__ == "__main__":
    unittest.main()
