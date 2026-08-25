from decimal import Decimal

from django.test import SimpleTestCase

from .pricing import calculate_multi_market_fee, ordered_market_ids


class MultiMarketPricingTests(SimpleTestCase):
    def test_single_market_has_no_fee(self):
        rate, fee = calculate_multi_market_fee([Decimal("500.00")])
        self.assertEqual(rate, Decimal("0.00"))
        self.assertEqual(fee, Decimal("0.00"))

    def test_combines_non_first_markets_before_rounding(self):
        rate, fee = calculate_multi_market_fee(
            [Decimal("100.00"), Decimal("110.00"), Decimal("98.00")]
        )
        self.assertEqual(rate, Decimal("5.00"))
        self.assertEqual(fee, Decimal("10.00"))

    def test_rounds_half_a_pound_up(self):
        _, lower_fee = calculate_multi_market_fee(
            [Decimal("100.00"), Decimal("208.00")]
        )
        _, half_fee = calculate_multi_market_fee([Decimal("100.00"), Decimal("210.00")])
        self.assertEqual(lower_fee, Decimal("10.00"))
        self.assertEqual(half_fee, Decimal("11.00"))

    def test_requested_order_is_a_validated_prefix(self):
        groups = {2: object(), 1: object(), 3: object()}
        self.assertEqual(ordered_market_ids(groups, [1]), [1, 2, 3])
        with self.assertRaises(ValueError):
            ordered_market_ids(groups, [4])
        with self.assertRaises(ValueError):
            ordered_market_ids(groups, [1, 1])
