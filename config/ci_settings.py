import os

import dj_database_url

from .test_settings import *  # noqa: F401,F403


DATABASES = {
    "default": dj_database_url.parse(
        os.environ.get(
            "CI_DATABASE_URL",
            os.environ.get(
                "DATABASE_URL",
                "postgresql://postgres@127.0.0.1:5433/yalla_test",
            ),
        ),
        conn_max_age=0,
    )
}
