class InMemoryRedis:
    """Small deterministic Redis substitute for task unit tests."""

    def __init__(self):
        self._values = {}

    def get(self, key):
        return self._values.get(key)

    def set(self, key, value, *, ex=None, nx=False):
        del ex
        if nx and key in self._values:
            return False
        self._values[key] = value
        return True

    def delete(self, *keys):
        deleted = 0
        for key in keys:
            deleted += int(self._values.pop(key, None) is not None)
        return deleted

    def keys(self, pattern):
        prefix = pattern.removesuffix("*")
        return [key for key in self._values if key.startswith(prefix)]

    def pipeline(self):
        return _InMemoryPipeline()


class _InMemoryPipeline:
    def hincrby(self, *args, **kwargs):
        return self

    def hincrbyfloat(self, *args, **kwargs):
        return self

    def expire(self, *args, **kwargs):
        return self

    def execute(self):
        return []
