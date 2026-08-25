from decimal import Decimal, ROUND_HALF_UP


MONEY_ZERO = Decimal("0.00")
MULTI_MARKET_FEE_RATE = Decimal("5.00")


def calculate_multi_market_fee(ordered_net_market_totals):
    """Return the saved rate and whole-pound fee for an ordered market list."""

    totals = [max(Decimal(value), MONEY_ZERO) for value in ordered_net_market_totals]
    if len(totals) <= 1:
        return MONEY_ZERO, MONEY_ZERO

    chargeable_total = sum(totals[1:], MONEY_ZERO)
    raw_fee = chargeable_total * MULTI_MARKET_FEE_RATE / Decimal("100")
    fee = raw_fee.quantize(Decimal("1"), rounding=ROUND_HALF_UP).quantize(
        Decimal("0.01")
    )
    return MULTI_MARKET_FEE_RATE, fee


def ordered_market_ids(groups, requested_order=None):
    """Apply a validated client prefix, then append missing groups stably."""

    available_ids = list(groups)
    requested_ids = list(requested_order or [])
    if len(requested_ids) != len(set(requested_ids)):
        raise ValueError("Market order cannot contain duplicate market IDs.")

    unknown_ids = [market_id for market_id in requested_ids if market_id not in groups]
    if unknown_ids:
        raise ValueError(
            f"Market order contains markets that are not in the order: {unknown_ids}."
        )

    requested_set = set(requested_ids)
    return requested_ids + [
        market_id for market_id in available_ids if market_id not in requested_set
    ]
