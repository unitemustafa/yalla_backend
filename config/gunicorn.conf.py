import os


def _positive_int(name, default):
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# Media uploads spend most of their time waiting on Cloudinary. A small pool of
# threaded workers keeps normal API traffic responsive while that I/O is in
# flight, without requiring a large container footprint.
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
access_log_format = (
    '%({x-forwarded-for}i)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s '
    'duration=%(L)s "%(f)s" "%(a)s"'
)
