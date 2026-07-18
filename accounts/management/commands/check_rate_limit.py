import uuid

from django.core.management.base import BaseCommand, CommandError
from django_redis import get_redis_connection
from redis.exceptions import RedisError

from config.rate_limit import LUA_RATE_LIMIT


class Command(BaseCommand):
    help = "Verify the rate-limit Redis connection and Lua execution."

    def handle(self, *args, **options):
        client = None
        suffix = uuid.uuid4().hex
        keys = [
            f"yalla:rate-limit:deployment-check:{suffix}:fixed",
            f"yalla:rate-limit:deployment-check:{suffix}:sliding",
        ]
        try:
            client = get_redis_connection("rate_limit")
            client.ping()
            sha = client.script_load(LUA_RATE_LIMIT)
            result = client.evalsha(
                sha,
                len(keys),
                *keys,
                suffix,
                2,
                "fixed",
                2,
                1_000,
                "sliding",
                2,
                1_000,
            )
        except RedisError as error:
            raise CommandError(
                f"Rate-limit Redis check failed: {error.__class__.__name__}"
            ) from error
        finally:
            if client is not None:
                for key in keys:
                    try:
                        client.delete(key)
                    except RedisError:
                        pass
        if list(result) != [1, 0, 0]:
            raise CommandError(
                "Rate-limit Lua script returned an invalid result."
            )
        self.stdout.write(
            self.style.SUCCESS("Rate-limit Redis and Lua checks passed.")
        )
