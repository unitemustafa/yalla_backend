import os
import runpy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase


CONFIG_PATH = Path(__file__).with_name("gunicorn.conf.py")


class GunicornConfigTests(SimpleTestCase):
    def load_config(self, config_path=CONFIG_PATH, **environment):
        with patch.dict(os.environ, environment, clear=True):
            return runpy.run_path(str(config_path))

    def test_defaults_allow_concurrent_blocking_uploads(self):
        config = self.load_config(PORT="8080")

        self.assertEqual(config["bind"], "0.0.0.0:8080")
        self.assertEqual(config["worker_class"], "gthread")
        self.assertEqual(config["workers"], 4)
        self.assertEqual(config["threads"], 2)
        self.assertEqual(config["timeout"], 120)
        self.assertEqual(config["graceful_timeout"], 30)
        self.assertEqual(config["keepalive"], 5)
        self.assertEqual(config["max_requests"], 1000)
        self.assertEqual(config["max_requests_jitter"], 100)
        self.assertIn("duration=%(L)s", config["access_log_format"])

    def test_environment_can_tune_container_limits(self):
        config = self.load_config(
            PORT="8081",
            WEB_CONCURRENCY="3",
            GUNICORN_THREADS="5",
            GUNICORN_TIMEOUT="90",
            GUNICORN_GRACEFUL_TIMEOUT="25",
            GUNICORN_KEEPALIVE="7",
            GUNICORN_MAX_REQUESTS="750",
            GUNICORN_MAX_REQUESTS_JITTER="75",
        )

        self.assertEqual(config["bind"], "0.0.0.0:8081")
        self.assertEqual(config["workers"], 3)
        self.assertEqual(config["threads"], 5)
        self.assertEqual(config["timeout"], 90)
        self.assertEqual(config["graceful_timeout"], 25)
        self.assertEqual(config["keepalive"], 7)
        self.assertEqual(config["max_requests"], 750)
        self.assertEqual(config["max_requests_jitter"], 75)

    def test_invalid_or_non_positive_values_fall_back_to_safe_defaults(self):
        config = self.load_config(
            WEB_CONCURRENCY="0",
            GUNICORN_THREADS="invalid",
            GUNICORN_TIMEOUT="-1",
            GUNICORN_GRACEFUL_TIMEOUT="",
            GUNICORN_KEEPALIVE="0",
            GUNICORN_MAX_REQUESTS="invalid",
            GUNICORN_MAX_REQUESTS_JITTER="-100",
        )

        self.assertEqual(config["workers"], 4)
        self.assertEqual(config["threads"], 2)
        self.assertEqual(config["timeout"], 120)
        self.assertEqual(config["graceful_timeout"], 30)
        self.assertEqual(config["keepalive"], 5)
        self.assertEqual(config["max_requests"], 1000)
        self.assertEqual(config["max_requests_jitter"], 100)

    def test_development_loads_local_dotenv_without_overriding_shell(self):
        with TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            config_dir = project_dir / "config"
            config_dir.mkdir()
            temporary_config = config_dir / CONFIG_PATH.name
            temporary_config.write_text(CONFIG_PATH.read_text())
            (project_dir / ".env").write_text(
                "PORT=8090\n"
                "WEB_CONCURRENCY=6\n"
                "GUNICORN_THREADS=7\n"
                "DOTENV_TEST_SENTINEL=local-only\n"
            )

            config = self.load_config(
                temporary_config,
                APP_ENV="development",
                WEB_CONCURRENCY="5",
            )

        self.assertEqual(config["bind"], "0.0.0.0:8090")
        self.assertEqual(config["workers"], 5)
        self.assertEqual(config["threads"], 7)
        self.assertNotIn("DOTENV_TEST_SENTINEL", os.environ)

    def test_production_does_not_load_local_dotenv(self):
        with TemporaryDirectory() as temporary_directory:
            project_dir = Path(temporary_directory)
            config_dir = project_dir / "config"
            config_dir.mkdir()
            temporary_config = config_dir / CONFIG_PATH.name
            temporary_config.write_text(CONFIG_PATH.read_text())
            (project_dir / ".env").write_text(
                "PORT=8090\nWEB_CONCURRENCY=6\nGUNICORN_THREADS=7\n"
            )

            config = self.load_config(temporary_config, APP_ENV="production")

        self.assertEqual(config["bind"], "0.0.0.0:8000")
        self.assertEqual(config["workers"], 4)
        self.assertEqual(config["threads"], 2)
