import logging
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.redis import RedisCache
from redis.exceptions import RedisError, ConnectionError, TimeoutError

logger = logging.getLogger(__name__)


class ResilientRedisCache(RedisCache):
    """
    Redis cache backend that gracefully handles Redis outages and timeouts.
    If Redis is unreachable, read operations fail-open (returning default/None as cache MISS),
    and write operations fail-soft (logging a warning and returning False),
    preventing application crashes during Redis maintenance or temporary outages.
    """

    def add(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        try:
            return super().add(key, value, timeout=timeout, version=version)
        except (RedisError, ConnectionError, TimeoutError, OSError) as exc:
            logger.warning("resilient_cache_add_failed key=%s error=%s", key, exc)
            return False

    def get(self, key, default=None, version=None):
        try:
            return super().get(key, default=default, version=version)
        except (RedisError, ConnectionError, TimeoutError, OSError) as exc:
            logger.warning("resilient_cache_get_failed key=%s error=%s", key, exc)
            return default

    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        try:
            return super().set(key, value, timeout=timeout, version=version)
        except (RedisError, ConnectionError, TimeoutError, OSError) as exc:
            logger.warning("resilient_cache_set_failed key=%s error=%s", key, exc)
            return False

    def touch(self, key, timeout=DEFAULT_TIMEOUT, version=None):
        try:
            return super().touch(key, timeout=timeout, version=version)
        except (RedisError, ConnectionError, TimeoutError, OSError) as exc:
            logger.warning("resilient_cache_touch_failed key=%s error=%s", key, exc)
            return False

    def delete(self, key, version=None):
        try:
            return super().delete(key, version=version)
        except (RedisError, ConnectionError, TimeoutError, OSError) as exc:
            logger.warning("resilient_cache_delete_failed key=%s error=%s", key, exc)
            return False

    def get_many(self, keys, version=None):
        try:
            return super().get_many(keys, version=version)
        except (RedisError, ConnectionError, TimeoutError, OSError) as exc:
            logger.warning("resilient_cache_get_many_failed error=%s", exc)
            return {}

    def set_many(self, data, timeout=DEFAULT_TIMEOUT, version=None):
        try:
            return super().set_many(data, timeout=timeout, version=version)
        except (RedisError, ConnectionError, TimeoutError, OSError) as exc:
            logger.warning("resilient_cache_set_many_failed error=%s", exc)
            return []

    def delete_many(self, keys, version=None):
        try:
            return super().delete_many(keys, version=version)
        except (RedisError, ConnectionError, TimeoutError, OSError) as exc:
            logger.warning("resilient_cache_delete_many_failed error=%s", exc)
            return False

    def clear(self):
        try:
            return super().clear()
        except (RedisError, ConnectionError, TimeoutError, OSError) as exc:
            logger.warning("resilient_cache_clear_failed error=%s", exc)
            return False
