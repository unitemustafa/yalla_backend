# Rate limiting

Nginx is the authoritative production request limiter. It applies a shared
per-client-IP limit before requests reach Gunicorn, so all Django workers see
the same protection without another runtime service.

Cloudflare client IPs are accepted only when the socket peer belongs to an
official Cloudflare network. Direct callers cannot spoof `CF-Connecting-IP`.

## Production

1. Keep `RATE_LIMIT_MODE=off` in `.env.production`.
2. Keep the Nginx shared-memory request and connection zones enabled.
3. Run `nginx -t` after changing the proxy configuration.
4. Run `python manage.py check --tag rate_limit` after changing policy values.
5. Verify repeated public requests through Cloudflare and review Nginx logs.

The Nginx template currently permits normal API bursts while rejecting abusive
traffic with HTTP 429. Adjust its rate and burst together after reviewing real
traffic; do not enable the Django limiter as a replacement in a multi-worker
deployment.

## Development and focused tests

Django contains an optional process-local limiter with fixed and sliding
windows. Its modes are:

- `off`: bypass application-level limiting.
- `observe`: evaluate policies and log blocks without rejecting requests.
- `enforce`: return HTTP 429 after a process-local policy is exceeded.

The application limiter is useful for policy tests and single-process local
development. Its counters are intentionally not shared across Gunicorn
workers, so production keeps it off and relies on Nginx.

Identity values and tokens are converted into keyed HMAC fingerprints before
being used as limiter keys. Proxy headers are ignored unless the direct peer is
inside `RATE_LIMIT_TRUSTED_PROXY_CIDRS`.

## Client contract

Enforced limits return HTTP 429, `Retry-After`, and:

```json
{
  "code": "rate_limited",
  "detail": "Too many requests. Try again later.",
  "retry_after_seconds": 42
}
```

OTP cooldowns use the same wait fields with `code: "otp_cooldown"`.
