# Rate limiting

The API uses a dedicated, non-sharded Redis/Valkey primary. General traffic
uses fixed windows while sensitive auth and side-effect operations use exact
sliding windows. One Lua script evaluates every applicable policy atomically;
rejected requests consume no quota from otherwise passing policies.

## Deployment

1. Provision Redis in the same region as the API and set the TLS connection in
   `RATE_LIMIT_REDIS_URL`.
2. Set the ingress client-IP header and the exact trusted proxy CIDRs. The
   header is ignored when the socket peer is not trusted.
3. Run `python manage.py check --tag rate_limit`.
4. Run `python manage.py check_rate_limit` to verify `PING`, `SCRIPT LOAD`, and
   multi-key `EVALSHA` against the deployment Redis. This deliberately fails
   on sharded/Cluster deployments, which are outside v1.
5. Deploy with `RATE_LIMIT_MODE=observe` and review `rate_limit_blocked` logs
   for 24-48 hours.
6. Switch to `enforce` with `RATE_LIMIT_ENFORCE_SCOPES` listing the sensitive
   scopes first. Remove the allowlist after a stable day to enforce every
   configured scope. An empty allowlist means all scopes.

`observe` and `enforce` have separate Redis namespaces. Redis errors explicitly
fail open and emit sampled `rate_limit_backend_error` logs. Set the mode to
`off` for an immediate rollback without reverting code.

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
