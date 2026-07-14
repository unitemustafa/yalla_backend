import os
import runpy
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase


CONFIG_PATH = Path(__file__).with_name("gunicorn.conf.py")


class GunicornConfigTests(SimpleTestCase):
    def load_config(self, **environment):
        with patch.dict(os.environ, environment, clear=True):
            return runpy.run_path(str(CONFIG_PATH))

    def test_defaults_allow_concurrent_blocking_uploads(self):
        config = self.load_config(PORT="8080")

        self.assertEqual(config["bind"], "0.0.0.0:8080")
        self.assertEqual(config["worker_class"], "gthread")
        self.assertEqual(config["workers"], 2)
        self.assertEqual(config["threads"], 4)
        self.assertEqual(config["timeout"], 120)
        self.assertIn("duration=%(L)s", config["access_log_format"])

    def test_environment_can_tune_container_limits(self):
        config = self.load_config(
            WEB_CONCURRENCY="3",
            GUNICORN_THREADS="2",
            GUNICORN_TIMEOUT="90",
        )

        self.assertEqual(config["workers"], 3)
        self.assertEqual(config["threads"], 2)
        self.assertEqual(config["timeout"], 90)

    def test_invalid_or_non_positive_values_fall_back_to_safe_defaults(self):
        config = self.load_config(
            WEB_CONCURRENCY="0",
            GUNICORN_THREADS="invalid",
        )

        self.assertEqual(config["workers"], 2)
        self.assertEqual(config["threads"], 4)
