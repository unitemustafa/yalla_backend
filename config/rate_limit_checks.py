import ipaddress

from django.conf import settings
from django.core.checks import Error, Warning, register

from .rate_limit import POLICIES, parse_rate


@register("rate_limit")
def check_rate_limit_configuration(app_configs, **kwargs):
    messages = []
    mode = getattr(settings, "RATE_LIMIT_MODE", "off").strip().lower()
    if mode not in {"off", "observe", "enforce"}:
        messages.append(
            Error(
                "RATE_LIMIT_MODE must be off, observe, or enforce.",
                id="rate_limit.E001",
            )
        )
    if mode == "enforce" and not getattr(settings, "RATE_LIMIT_REDIS_URL", ""):
        messages.append(
            Error(
                "RATE_LIMIT_REDIS_URL is required in enforce mode.",
                id="rate_limit.E002",
            )
        )
    rate_limit_secret = getattr(settings, "RATE_LIMIT_KEY_SECRET", "")
    if mode in {"observe", "enforce"} and (
        not str(rate_limit_secret).strip()
        or rate_limit_secret == getattr(settings, "SECRET_KEY", "")
    ):
        messages.append(
            Error(
                "RATE_LIMIT_KEY_SECRET must be set explicitly and must be "
                "different from Django SECRET_KEY in observe or enforce mode.",
                id="rate_limit.E007",
            )
        )

    cidrs = getattr(settings, "RATE_LIMIT_TRUSTED_PROXY_CIDRS", ())
    for value in cidrs:
        try:
            ipaddress.ip_network(value, strict=False)
        except ValueError:
            messages.append(
                Error(
                    f"Invalid trusted proxy CIDR: {value}",
                    id="rate_limit.E003",
                )
            )
    if mode != "off" and getattr(settings, "RATE_LIMIT_CLIENT_IP_HEADER", "") and not cidrs:
        messages.append(
            Warning(
                "Client-IP header is configured but no trusted proxy CIDRs are set; the limiter will safely use REMOTE_ADDR.",
                id="rate_limit.W001",
            )
        )

    rates_by_scope = getattr(settings, "RATE_LIMIT_POLICY_RATES", {})
    for scope in getattr(settings, "RATE_LIMIT_ENFORCE_SCOPES", ()):
        if scope not in POLICIES:
            messages.append(
                Error(
                    f"Unknown enforce rate limit scope: {scope}",
                    id="rate_limit.E006",
                )
            )
    for scope, rates in rates_by_scope.items():
        if scope not in POLICIES:
            messages.append(
                Error(
                    f"Unknown rate limit scope: {scope}",
                    id="rate_limit.E004",
                )
            )
            continue
        for rate in rates:
            try:
                parse_rate(rate)
            except ValueError as error:
                messages.append(
                    Error(str(error), id="rate_limit.E005")
                )
    return messages
