from unittest.mock import patch

from django.core.cache.backends.redis import RedisCache
from django.test import SimpleTestCase
from redis.exceptions import ConnectionError

from .cache import ResilientRedisCache


class ResilientRedisCacheTests(SimpleTestCase):
    def setUp(self):
        self.cache = object.__new__(ResilientRedisCache)

    def test_redis_outage_turns_reads_into_misses_and_writes_into_soft_failures(self):
        operations = (
            ("add", ("key", "value"), False),
            ("get", ("key",), "fallback"),
            ("set", ("key", "value"), False),
            ("touch", ("key",), False),
            ("delete", ("key",), False),
            ("get_many", (["key"],), {}),
            ("set_many", ({"key": "value"},), []),
            ("delete_many", (["key"],), False),
            ("clear", (), False),
        )
        for name, args, expected in operations:
            with self.subTest(operation=name):
                with patch.object(RedisCache, name, side_effect=ConnectionError("offline")):
                    with self.assertLogs("config.cache", level="WARNING"):
                        actual = getattr(self.cache, name)(
                            *args, **({"default": "fallback"} if name == "get" else {})
                        )
                    self.assertEqual(actual, expected)

    def test_healthy_redis_results_are_preserved(self):
        operations = (
            ("add", ("key", "value"), True),
            ("get", ("key",), "value"),
            ("set", ("key", "value"), None),
            ("touch", ("key",), True),
            ("delete", ("key",), True),
            ("get_many", (["key"],), {"key": "value"}),
            ("set_many", ({"key": "value"},), []),
            ("delete_many", (["key"],), None),
            ("clear", (), True),
        )
        for name, args, expected in operations:
            with self.subTest(operation=name):
                with patch.object(RedisCache, name, return_value=expected):
                    self.assertEqual(getattr(self.cache, name)(*args), expected)
