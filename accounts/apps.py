from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = 'accounts'

    def ready(self):
        # Importing registers deployment checks without opening a Redis
        # connection during Django startup.
        from config import rate_limit_checks  # noqa: F401
