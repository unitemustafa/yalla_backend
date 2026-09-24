import logging
import os
import time
from typing import Tuple, Optional
import redis
from redis.connection import ConnectionPool
from redis.exceptions import RedisError, ConnectionError, TimeoutError

logger = logging.getLogger(__name__)

# Connection pools indexed by URL
_POOLS: dict[str, ConnectionPool] = {}


def get_redis_url(purpose: str = "default") -> str:
    default_url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    if purpose == "cache":
        return os.environ.get(
            "REDIS_CACHE_URL", os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/1")
        )
    elif purpose == "rate_limit":
        return os.environ.get(
            "REDIS_RATE_LIMIT_URL",
            os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/2"),
        )
    return default_url


def get_redis_client(purpose: str = "default", db: Optional[int] = None) -> redis.Redis:
    url = get_redis_url(purpose)
    if db is not None:
        # Override DB number if specified
        base = url.rsplit("/", 1)[0]
        url = f"{base}/{db}"

    if url not in _POOLS:
        _POOLS[url] = ConnectionPool.from_url(
            url,
            max_connections=int(os.environ.get("REDIS_MAX_CONNECTIONS", "50")),
            socket_connect_timeout=float(
                os.environ.get("REDIS_CONNECT_TIMEOUT", "0.5")
            ),
            socket_timeout=float(os.environ.get("REDIS_SOCKET_TIMEOUT", "0.5")),
            retry_on_timeout=True,
            health_check_interval=int(
                os.environ.get("REDIS_HEALTH_CHECK_INTERVAL", "0")
            ),
            protocol=3,
        )
    return redis.Redis(connection_pool=_POOLS[url])


def check_redis_health(purpose: str = "default") -> Tuple[bool, float, Optional[str]]:
    """Checks Redis connectivity and measures latency in milliseconds."""
    t0 = time.perf_counter()
    try:
        client = get_redis_client(purpose)
        client.ping()
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return True, latency_ms, None
    except (RedisError, ConnectionError, TimeoutError, Exception) as exc:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        logger.warning("redis_health_check_failed purpose=%s error=%s", purpose, exc)
        return False, latency_ms, str(exc)
