# Rate limiting

Nginx applies a shared per-client-IP request limit before requests reach
Gunicorn. Django uses Redis for shared, identity-aware limits on authentication
and OTP endpoints across all workers.

Cloudflare client IPs are accepted only when the socket peer belongs to an
official Cloudflare network. Direct callers cannot spoof `CF-Connecting-IP`.

## Production

1. Set a separate, random `RATE_LIMIT_KEY_SECRET` in `.env.production`.
2. Keep the Nginx shared-memory request and connection zones enabled.
3. Keep the Redis-backed auth scope enforcement in `compose.yaml` enabled.
4. Run `nginx -t` and `python manage.py check --tag rate_limit` after changing policy values.
5. Verify repeated auth requests through Cloudflare and review 429 responses.

The Nginx template currently permits normal API bursts while rejecting abusive
traffic with HTTP 429. The Django limiter adds email, token, and IP limits for
login, signup, OTP, and refresh requests. Redis stores those counters; if it is
unavailable, admin login and OTP verification fail closed while other scopes
fall back to process-local limits.

## Development and focused tests

Django supports Redis-backed counters or process-local fixed and sliding
windows. Its modes are:

- `off`: bypass application-level limiting.
- `observe`: evaluate policies and log blocks without rejecting requests.
- `enforce`: return HTTP 429 after a policy is exceeded.

The process-local counters are useful for focused tests and as a fallback.
Production uses Redis so authentication limits remain shared across Gunicorn
workers.

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
