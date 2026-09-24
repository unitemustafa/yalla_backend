import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("yalla")

# Read configuration from Django settings using the 'CELERY' namespace
app.config_from_object("django.conf:settings", namespace="CELERY")

# Autodiscover tasks in all installed Django apps
app.autodiscover_tasks()
