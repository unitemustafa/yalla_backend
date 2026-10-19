import unittest

from tools.performance.sanitize_logs import sanitize


class SanitizeLogsTests(unittest.TestCase):
    def test_handles_nul_padded_powershell_diagnostic_text(self):
        raw = "\x00".join("I/flutter ( 999): unrelated device log")
        cleaned, removed = sanitize(raw)
        self.assertEqual(removed, 1)
        self.assertNotIn("unrelated", cleaned)

    def test_keeps_failed_measurements_and_removes_unrelated_android_logs(self):
        raw = "\n".join(
            [
                "I/flutter ( 123): 00:00 +0: physical Android customer UI baseline",
                "I/flutter ( 999): personal unrelated application log",
                "I/flutter ( 123): Test failed: late frame 101ms",
                "DriverError: service disposed",
            ]
        )
        cleaned, removed = sanitize(raw)
        self.assertEqual(removed, 1)
        self.assertNotIn("personal", cleaned)
        self.assertIn("Test failed: late frame 101ms", cleaned)
        self.assertIn("DriverError", cleaned)

    def test_redacts_identifiers_without_android_prefix(self):
        cleaned, _ = sanitize(
            "VM at http://127.0.0.1:1234/secret=/ Bearer abc.def AA:BB:CC:DD:EE:FF"
        )
        self.assertNotIn("secret", cleaned)
        self.assertNotIn("abc.def", cleaned)
        self.assertNotIn("AA:BB", cleaned)


if __name__ == "__main__":
    unittest.main()
