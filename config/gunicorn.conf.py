import os


def _positive_int(name, default):
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# Image uploads perform bounded Pillow work before writing to the local media
# volume. A small thread pool keeps other requests responsive during that work.
worker_class = "gthread"
workers = _positive_int("WEB_CONCURRENCY", 2)
threads = _positive_int("GUNICORN_THREADS", 4)

timeout = _positive_int("GUNICORN_TIMEOUT", 120)
graceful_timeout = _positive_int("GUNICORN_GRACEFUL_TIMEOUT", 30)
keepalive = _positive_int("GUNICORN_KEEPALIVE", 5)

max_requests = _positive_int("GUNICORN_MAX_REQUESTS", 1000)
max_requests_jitter = _positive_int("GUNICORN_MAX_REQUESTS_JITTER", 100)

accesslog = "-"
errorlog = "-"
capture_output = True

# Gunicorn 26 enables a local control socket by default. Containers are
# immutable outside the mounted data directories and this deployment does not
# use the control interface, so disable it instead of writing under /app.
control_socket_disable = True

access_log_format = (
    '%({x-forwarded-for}i)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s '
    'duration=%(L)s "%(f)s" "%(a)s"'
)
