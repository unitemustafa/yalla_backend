import hashlib
import hmac
import ipaddress
import logging
import math
import random
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from functools import lru_cache, wraps

from django.conf import settings
from django.http import JsonResponse
from rest_framework.throttling import BaseThrottle


logger = logging.getLogger(__name__)

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
RATE_RE = re.compile(r"^(?P<count>[1-9]\d*)/(?P<amount>[1-9]\d*)(?P<unit>[smhd])$")
WINDOW_UNITS_MS = {
    "s": 1_000,
    "m": 60_000,
    "h": 3_600_000,
    "d": 86_400_000,
}


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


@dataclass
class _FixedWindowState:
    count: int
    reset_ms: int


@dataclass
class _SlidingWindowState:
    timestamps: list[int]
    window_ms: int


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
    "geocoding_user": PolicyDefinition("sliding", "user"),
    "geocoding_global": PolicyDefinition("sliding", "global"),
}


_state_lock = threading.Lock()
_fixed_windows = {}
_sliding_windows = {}
_last_cleanup_ms = 0


def _clear_rate_limit_state():
    global _last_cleanup_ms
    with _state_lock:
        _fixed_windows.clear()
        _sliding_windows.clear()
        _last_cleanup_ms = 0


def _cleanup_rate_limit_state(now_ms):
    global _last_cleanup_ms
    if now_ms - _last_cleanup_ms < 60_000:
        return
    _last_cleanup_ms = now_ms
    expired_fixed = [
        key for key, state in _fixed_windows.items() if state.reset_ms <= now_ms
    ]
    for key in expired_fixed:
        _fixed_windows.pop(key, None)
    for key, state in tuple(_sliding_windows.items()):
        cutoff = now_ms - state.window_ms
        state.timestamps[:] = [
            timestamp for timestamp in state.timestamps if timestamp > cutoff
        ]
        if not state.timestamps:
            _sliding_windows.pop(key, None)


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
    except Exception:
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
    if policy.identity == "global":
        return _fingerprint("global", "geoapify")
    value = _request_value(request, policy.fields)
    if not value:
        return ""
    if policy.identity == "identifier":
        value = _normalize_identifier(value)
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
    namespace = f"yalla:rate-limit:local:{mode}:v1"
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


def _evaluate_rules(rules):
    now_ms = int(time.monotonic() * 1000)
    with _state_lock:
        _cleanup_rate_limit_state(now_ms)
        fixed_snapshots = {}
        sliding_snapshots = {}
        failed = []
        max_wait_ms = 0

        for rule in rules:
            if rule.algorithm == "fixed":
                state = _fixed_windows.get(rule.key)
                if state is None or state.reset_ms <= now_ms:
                    state = _FixedWindowState(0, now_ms + rule.window_ms)
                fixed_snapshots[rule.key] = state
                if state.count >= rule.limit:
                    failed.append(rule.scope)
                    max_wait_ms = max(max_wait_ms, state.reset_ms - now_ms)
                continue

            state = _sliding_windows.get(rule.key)
            timestamps = [] if state is None else state.timestamps
            cutoff = now_ms - rule.window_ms
            active_timestamps = [value for value in timestamps if value > cutoff]
            sliding_snapshots[rule.key] = active_timestamps
            if len(active_timestamps) >= rule.limit:
                failed.append(rule.scope)
                max_wait_ms = max(
                    max_wait_ms,
                    active_timestamps[0] + rule.window_ms - now_ms,
                )

        if failed:
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=max(1, math.ceil(max_wait_ms / 1000)),
                blocked_scopes=tuple(dict.fromkeys(failed)),
            )

        for rule in rules:
            if rule.algorithm == "fixed":
                state = fixed_snapshots[rule.key]
                _fixed_windows[rule.key] = _FixedWindowState(
                    count=state.count + 1,
                    reset_ms=state.reset_ms,
                )
            else:
                _sliding_windows[rule.key] = _SlidingWindowState(
                    timestamps=[*sliding_snapshots[rule.key], now_ms],
                    window_ms=rule.window_ms,
                )
        return RateLimitDecision(allowed=True)


def _should_log():
    rate = float(getattr(settings, "RATE_LIMIT_LOG_SAMPLE_RATE", 0.1))
    return rate >= 1 or (rate > 0 and random.random() < rate)


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

    decision = _evaluate_rules(rules)
    if not decision.allowed and _should_log():
        logger.info(
            "rate_limit_blocked mode=%s method=%s path=%s scopes=%s wait=%s",
            mode,
            request.method,
            getattr(request, "path", ""),
            ",".join(decision.blocked_scopes),
            decision.retry_after_seconds,
        )
    return decision


class YallaRateThrottle(BaseThrottle):
    def __init__(self):
        self._wait = None

    def allow_request(self, request, view):
        mode = rate_limit_mode()
        if mode == "off" or is_rate_limit_exempt(request):
            return True
        scopes = scopes_for_request(request, view=view)
        decision = evaluate_rate_limit(request, scopes)
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
            scopes = scopes_for_request(
                request,
                explicit_scopes=explicit_scopes,
            )
            decision = evaluate_rate_limit(request, scopes)
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
