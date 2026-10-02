"""Safety regressions for backup retention and partial/offsite failures.

Run on Linux: python -m unittest discover -s tools -p test_backup_script.py.
No production environment or Docker daemon is used; the CLI is substituted.
"""

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipIf(os.name == "nt", "Requires a POSIX shell and flock")
class BackupScriptTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="yalla-backup-test-")
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        deploy = self.root / "project" / "deploy"
        deploy.mkdir(parents=True)
        self.script = deploy / "backup.sh"
        # A Windows checkout may have CRLF; Linux release checkouts use LF.
        source = Path(__file__).resolve().parents[1] / "deploy" / "backup.sh"
        self.script.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        self.backups = self.root / "backups with spaces"
        self.backups.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self._cli("docker", """case " $* " in
*" ps "*) printf 'postgres\\n';;
*" pg_dump "*) [ "${FAIL_DUMP:-0}" = 0 ] || exit 9; printf 'test-dump';;
*) exit 8;;
esac
""")
        self._cli("rclone", "[ \"${FAIL_OFFSITE:-0}\" = 0 ] || exit 7\n")
        self.env_file = self.root / "test.env"
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}")

    def _cli(self, name, source):
        path = self.bin / name
        path.write_text("#!/bin/sh\nset -eu\n" + source, encoding="utf-8")
        path.chmod(0o700)

    def _backup(self, name, *, complete=True):
        folder = self.backups / name
        folder.mkdir()
        (folder / "postgres.dump").write_bytes(b"test-dump")
        checksum = hashlib.sha256(b"test-dump").hexdigest()
        (folder / "SHA256SUMS").write_text(f"{checksum}  postgres.dump\n", encoding="utf-8")
        if complete:
            (folder / ".yalla-backup").write_text("yalla-backup-v1\n", encoding="utf-8")
        return folder

    def _run(self, *, keep="2", offsite="", **overrides):
        self.env_file.write_text(
            f"YALLA_DATA_ROOT={self.root}\nYALLA_BACKUP_ROOT={self.backups}\n"
            f"YALLA_BACKUP_KEEP_COUNT={keep}\nYALLA_BACKUP_RCLONE_REMOTE={offsite}\n",
            encoding="utf-8",
        )
        return subprocess.run(
            ["sh", str(self.script), str(self.env_file)],
            env=dict(self.env, **overrides), capture_output=True, text=True, check=False,
        )

    def test_prunes_only_complete_owned_backups_and_preserves_external_symlink(self):
        oldest = self._backup("20000101T000000Z")
        retained = self._backup("20000102T000000Z")
        partial = self._backup("20000103T000000Z", complete=False)
        corrupt = self._backup("20000104T000000Z")
        (corrupt / "postgres.dump").write_bytes(b"corrupt")
        outside = self.root / "important"
        outside.mkdir()
        (outside / "keep").write_text("important", encoding="utf-8")
        link = self.backups / "19900101T000000Z"
        link.symlink_to(outside, target_is_directory=True)
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(oldest.exists())
        for folder in (retained, partial, corrupt, outside, link):
            self.assertTrue(folder.exists(), folder)
        self.assertEqual((outside / "keep").read_text(), "important")

    def test_dump_failure_does_not_mark_complete_or_prune(self):
        old = self._backup("20000101T000000Z")
        result = self._run(keep="1", FAIL_DUMP="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(old.exists())
        self.assertEqual(len(list(self.backups.glob("*/.yalla-backup"))), 1)

    def test_offsite_failure_keeps_every_local_backup(self):
        old = self._backup("20000101T000000Z")
        result = self._run(keep="1", offsite="backup:yalla-private", FAIL_OFFSITE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(old.exists())
        self.assertFalse((self.backups / ".last-offsite-success").exists())

    def test_verified_offsite_allows_retention(self):
        old = self._backup("20000101T000000Z")
        result = self._run(keep="1", offsite="backup:yalla-private")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(old.exists())
        self.assertTrue((self.backups / ".last-offsite-success").exists())

    def test_rejects_invalid_retention_without_changing_existing_backups(self):
        old = self._backup("20000101T000000Z")
        for value in ("0", "000", "-1", "wrong", "999999999999999999999", "366"):
            with self.subTest(value=value):
                self.assertNotEqual(self._run(keep=value).returncode, 0)
                self.assertTrue(old.exists())

    def test_rejects_remote_root_or_local_destination(self):
        for target in ("backup:", "/local/path", "backup:../outside"):
            with self.subTest(target=target):
                self.assertNotEqual(self._run(offsite=target).returncode, 0)


if __name__ == "__main__":
    unittest.main()
