import hashlib
import hmac
import ipaddress
import logging
import math
import random
import re
import threading
import unicodedata
import uuid
from dataclasses import dataclass
from functools import lru_cache, wraps

from django.conf import settings
from django.http import JsonResponse
from django_redis import get_redis_connection
from redis.exceptions import NoScriptError, RedisError
from rest_framework.throttling import BaseThrottle


logger = logging.getLogger(__name__)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
RATE_RE = re.compile(r"^(?P<count>[1-9]\d*)/(?P<amount>[1-9]\d*)(?P<unit>[smhd])$")
WINDOW_UNITS_MS = {
    "s": 1_000,
    "m": 60_000,
    "h": 3_600_000,
    "d": 86_400_000,
}


LUA_RATE_LIMIT = r"""
local timestamp = redis.call('TIME')
local now_ms = (tonumber(timestamp[1]) * 1000) + math.floor(tonumber(timestamp[2]) / 1000)
local member = ARGV[1]
local rule_count = tonumber(ARGV[2])
local allowed = 1
local max_wait_ms = 0
local failed = {}
local fixed_counts = {}
local fixed_resets = {}

for i = 1, rule_count do
    local offset = 3 + ((i - 1) * 3)
    local algorithm = ARGV[offset]
    local limit = tonumber(ARGV[offset + 1])
    local window_ms = tonumber(ARGV[offset + 2])
    local key = KEYS[i]

    if algorithm == 'fixed' then
        local state = redis.call('HMGET', key, 'count', 'reset_ms')
        local count = tonumber(state[1]) or 0
        local reset_ms = tonumber(state[2]) or 0
        if reset_ms <= now_ms then
            count = 0
            reset_ms = now_ms + window_ms
        end
        fixed_counts[i] = count
        fixed_resets[i] = reset_ms
        if count >= limit then
            allowed = 0
            local wait_ms = math.max(1, reset_ms - now_ms)
            if wait_ms > max_wait_ms then max_wait_ms = wait_ms end
            table.insert(failed, i)
        end
    else
        local cutoff = now_ms - window_ms
        redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
        local count = redis.call('ZCARD', key)
        if count >= limit then
            allowed = 0
            local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
            local oldest_ms = tonumber(oldest[2]) or now_ms
            local wait_ms = math.max(1, (oldest_ms + window_ms) - now_ms)
            if wait_ms > max_wait_ms then max_wait_ms = wait_ms end
            table.insert(failed, i)
        end
    end
end

-- All-or-none: a rejected request changes no enforcement counter. Cleanup of
-- expired sorted-set entries above is safe and does not consume capacity.
if allowed == 1 then
    for i = 1, rule_count do
        local offset = 3 + ((i - 1) * 3)
        local algorithm = ARGV[offset]
        local window_ms = tonumber(ARGV[offset + 2])
        local key = KEYS[i]
        if algorithm == 'fixed' then
            local next_count = fixed_counts[i] + 1
            local reset_ms = fixed_resets[i]
            redis.call('HSET', key, 'count', next_count, 'reset_ms', reset_ms)
            redis.call('PEXPIRE', key, math.max(1000, (reset_ms - now_ms) + 1000))
        else
            redis.call('ZADD', key, now_ms, member)
            redis.call('PEXPIRE', key, window_ms + 1000)
        end
    end
end

local response = {allowed, max_wait_ms, #failed}
for _, index in ipairs(failed) do table.insert(response, index) end
return response
"""


@dataclass(frozen=True)
class PolicyDefinition:
    algorithm: str
    identity: str
    fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class RateRule:
    scope: str
    algorithm: str
    limit: int
    window_ms: int
    key: str


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0
    blocked_scopes: tuple[str, ...] = ()
    backend_error: bool = False


POLICIES = {
    "api_anon": PolicyDefinition("fixed", "ip"),
    "api_user": PolicyDefinition("fixed", "user"),
    "api_write": PolicyDefinition("fixed", "user"),
    "login_ip": PolicyDefinition("sliding", "ip"),
    "login_identifier": PolicyDefinition(
        "sliding", "identifier", ("identifier", "email")
    ),
    "admin_login_ip": PolicyDefinition("sliding", "ip"),
    "admin_login_identifier": PolicyDefinition(
        "sliding", "identifier", ("identifier", "email")
    ),
    "signup_ip": PolicyDefinition("sliding", "ip"),
    "signup_email": PolicyDefinition("sliding", "identifier", ("email",)),
    "availability_ip": PolicyDefinition("fixed", "ip"),
    "otp_send_ip": PolicyDefinition("sliding", "ip"),
    "otp_send_identifier": PolicyDefinition(
        "sliding", "identifier", ("email",)
    ),
    "otp_verify_ip": PolicyDefinition("sliding", "ip"),
    "otp_verify_identifier": PolicyDefinition(
        "sliding", "identifier", ("email",)
    ),
    "refresh_ip": PolicyDefinition("sliding", "ip"),
    "refresh_token": PolicyDefinition(
        "sliding", "token", ("refreshToken", "refresh")
    ),
    "order_preview_user": PolicyDefinition("fixed", "user"),
    "order_create_user": PolicyDefinition("sliding", "user"),
    "upload_user": PolicyDefinition("sliding", "user"),
    "notification_send_user": PolicyDefinition("sliding", "user"),
    "snapshot_ip": PolicyDefinition("fixed", "ip"),
    "share_ip": PolicyDefinition("fixed", "ip"),
}


_script_sha = None
_script_lock = threading.Lock()


def rate_limit_mode():
    mode = getattr(settings, "RATE_LIMIT_MODE", "off").strip().lower()
    return mode if mode in {"off", "observe", "enforce"} else "off"


def is_rate_limit_exempt(request):
    if request.method.upper() == "OPTIONS":
        return True
    path = getattr(request, "path", "")
    return path in set(getattr(settings, "RATE_LIMIT_EXEMPT_PATHS", ()))


@lru_cache(maxsize=32)
def _trusted_networks(cidrs):
    networks = []
    for value in cidrs:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def _parsed_ip(value):
    if not value:
        return None
    try:
        return ipaddress.ip_address(str(value).strip())
    except ValueError:
        return None


def _is_trusted_proxy(address, networks):
    return bool(address and any(address in network for network in networks))


def _meta_header_name(value):
    name = (value or "").strip().upper().replace("-", "_")
    if not name:
        return ""
    return name if name.startswith("HTTP_") else f"HTTP_{name}"


def client_ip(request):
    remote = _parsed_ip(request.META.get("REMOTE_ADDR"))
    cidrs = tuple(getattr(settings, "RATE_LIMIT_TRUSTED_PROXY_CIDRS", ()))
    networks = _trusted_networks(cidrs)
    header_name = _meta_header_name(
        getattr(settings, "RATE_LIMIT_CLIENT_IP_HEADER", "")
    )

    if header_name and _is_trusted_proxy(remote, networks):
        raw_header = request.META.get(header_name, "")
        chain = [_parsed_ip(item) for item in str(raw_header).split(",")]
        if chain and all(chain):
            # The socket peer is the final proxy. Walk right-to-left past every
            # configured trusted proxy and select the first untrusted address.
            for address in reversed([*chain, remote]):
                if not _is_trusted_proxy(address, networks):
                    return address.compressed

    return remote.compressed if remote else "unknown"


def _fingerprint(kind, raw_value):
    secret = str(getattr(settings, "RATE_LIMIT_KEY_SECRET", settings.SECRET_KEY))
    payload = f"{kind}:{raw_value}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _normalize_identifier(value):
    normalized = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    if "@" in normalized:
        return normalized

    compact = re.sub(r"[\s().-]", "", normalized)
    if not re.fullmatch(r"\+?\d+", compact):
        return normalized
    if compact.startswith("00"):
        compact = f"+{compact[2:]}"
    if compact.startswith("213"):
        compact = f"+{compact}"
    elif re.fullmatch(r"0[567]\d{8}", compact):
        compact = f"+213{compact[1:]}"
    elif re.fullmatch(r"[567]\d{8}", compact):
        compact = f"+213{compact}"
    elif compact.startswith("20"):
        compact = f"+{compact}"
    elif compact.startswith("0"):
        compact = f"+20{compact[1:]}"
    return compact


def _request_value(request, fields):
    try:
        data = request.data
    except Exception:  # Parsers may reject malformed requests later in DRF.
        return ""
    for field in fields:
        value = data.get(field) if hasattr(data, "get") else None
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _identity_for_policy(request, policy):
    if policy.identity == "ip":
        return _fingerprint("ip", client_ip(request))
    if policy.identity == "user":
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return ""
        return _fingerprint("user", user.pk)
    value = _request_value(request, policy.fields)
    if not value:
        return ""
    if policy.identity == "identifier":
        value = _normalize_identifier(value)
    # Token fingerprints deliberately preserve case because JWT/base64 token
    # material is case-sensitive.
    return _fingerprint(policy.identity, value)


def parse_rate(value):
    match = RATE_RE.fullmatch(str(value).strip().lower())
    if not match:
        raise ValueError(f"Invalid rate limit value: {value!r}")
    count = int(match.group("count"))
    window_ms = (
        int(match.group("amount")) * WINDOW_UNITS_MS[match.group("unit")]
    )
    return count, window_ms


def scopes_for_request(request, view=None, explicit_scopes=()):
    scopes = []
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        scopes.append("api_user")
        if request.method.upper() in MUTATING_METHODS:
            scopes.append("api_write")
    else:
        scopes.append("api_anon")

    configured = explicit_scopes
    if view is not None:
        configured = getattr(view, "rate_limit_scopes", ())
        if isinstance(configured, dict):
            configured = configured.get(
                request.method.upper(), configured.get("*", ())
            )
    scopes.extend(configured or ())

    content_type = str(getattr(request, "content_type", "") or "").lower()
    if (
        request.method.upper() in MUTATING_METHODS
        and content_type.startswith("multipart/")
        and user
        and user.is_authenticated
    ):
        scopes.append("upload_user")

    return tuple(dict.fromkeys(scopes))


def build_rules(request, scopes, mode):
    rules = []
    rates_by_scope = getattr(settings, "RATE_LIMIT_POLICY_RATES", {})
    namespace = f"yalla:rate-limit:{mode}:v1"
    for scope in scopes:
        policy = POLICIES.get(scope)
        if policy is None:
            continue
        identity = _identity_for_policy(request, policy)
        if not identity:
            continue
        for rate in rates_by_scope.get(scope, ()):
            limit, window_ms = parse_rate(rate)
            key = f"{namespace}:{scope}:{identity}:{limit}:{window_ms}"
            rules.append(
                RateRule(
                    scope=scope,
                    algorithm=policy.algorithm,
                    limit=limit,
                    window_ms=window_ms,
                    key=key,
                )
            )
    return tuple(rules)


def _redis_client():
    return get_redis_connection("rate_limit")


def _load_script(client):
    global _script_sha
    with _script_lock:
        _script_sha = client.script_load(LUA_RATE_LIMIT)
        return _script_sha


def _execute_script(client, rules):
    global _script_sha
    sha = _script_sha or _load_script(client)
    keys = [rule.key for rule in rules]
    args = [uuid.uuid4().hex, len(rules)]
    for rule in rules:
        args.extend((rule.algorithm, rule.limit, rule.window_ms))
    try:
        return client.evalsha(sha, len(keys), *keys, *args)
    except NoScriptError:
        sha = _load_script(client)
        return client.evalsha(sha, len(keys), *keys, *args)


def _should_log():
    rate = float(getattr(settings, "RATE_LIMIT_LOG_SAMPLE_RATE", 0.1))
    return rate >= 1 or (rate > 0 and random.random() < rate)


def _log_backend_error(request, error):
    if _should_log():
        logger.warning(
            "rate_limit_backend_error method=%s path=%s error=%s",
            request.method,
            getattr(request, "path", ""),
            error.__class__.__name__,
        )


def _record_blocked_telemetry(client, mode, scopes):
    try:
        pipeline = client.pipeline(transaction=False)
        for scope in scopes:
            key = f"yalla:rate-limit:telemetry:v1:{mode}:blocked:{scope}"
            pipeline.incr(key)
            pipeline.expire(key, 172_800)
        pipeline.execute()
    except RedisError:
        # Enforcement already completed. Telemetry must never change the API
        # decision or trigger a second Redis failure path.
        return


def evaluate_rate_limit(request, scopes):
    mode = rate_limit_mode()
    if mode == "off" or is_rate_limit_exempt(request):
        return RateLimitDecision(allowed=True)
    if mode == "enforce":
        enabled_scopes = tuple(
            getattr(settings, "RATE_LIMIT_ENFORCE_SCOPES", ())
        )
        if enabled_scopes:
            scopes = tuple(scope for scope in scopes if scope in enabled_scopes)
    rules = build_rules(request, scopes, mode)
    if not rules:
        return RateLimitDecision(allowed=True)

    try:
        client = _redis_client()
        result = _execute_script(client, rules)
    except RedisError as error:
        _log_backend_error(request, error)
        return RateLimitDecision(allowed=True, backend_error=True)

    allowed = bool(int(result[0]))
    if allowed:
        return RateLimitDecision(allowed=True)

    retry_after = max(1, math.ceil(int(result[1]) / 1000))
    failed_count = int(result[2])
    failed_indexes = [int(value) - 1 for value in result[3 : 3 + failed_count]]
    blocked_scopes = tuple(
        dict.fromkeys(
            rules[index].scope
            for index in failed_indexes
            if 0 <= index < len(rules)
        )
    )
    _record_blocked_telemetry(client, mode, blocked_scopes)
    if _should_log():
        logger.info(
            "rate_limit_blocked mode=%s method=%s path=%s scopes=%s wait=%s",
            mode,
            request.method,
            getattr(request, "path", ""),
            ",".join(blocked_scopes),
            retry_after,
        )
    return RateLimitDecision(
        allowed=False,
        retry_after_seconds=retry_after,
        blocked_scopes=blocked_scopes,
    )


class YallaRateThrottle(BaseThrottle):
    def __init__(self):
        self._wait = None

    def allow_request(self, request, view):
        mode = rate_limit_mode()
        if mode == "off" or is_rate_limit_exempt(request):
            return True
        decision = evaluate_rate_limit(
            request,
            scopes_for_request(request, view=view),
        )
        if decision.allowed or mode == "observe":
            return True
        self._wait = decision.retry_after_seconds
        return False

    def wait(self):
        return self._wait


def rate_limit_view(*explicit_scopes):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            mode = rate_limit_mode()
            if mode == "off" or is_rate_limit_exempt(request):
                return view_func(request, *args, **kwargs)
            decision = evaluate_rate_limit(
                request,
                scopes_for_request(request, explicit_scopes=explicit_scopes),
            )
            if decision.allowed or mode == "observe":
                return view_func(request, *args, **kwargs)
            response = JsonResponse(
                {
                    "code": "rate_limited",
                    "detail": "Too many requests. Try again later.",
                    "retry_after_seconds": decision.retry_after_seconds,
                },
                status=429,
            )
            response.headers["Retry-After"] = str(
                decision.retry_after_seconds
            )
            return response

        return wrapped

    return decorator
