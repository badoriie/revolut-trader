"""Unit tests for trading fee calculation utilities (src/utils/fees.py).

Fee schedule under test:
  - LIMIT orders (maker): 0%
  - MARKET orders (taker): 0.09% = Decimal("0.0009")
"""

from decimal import Decimal

from src.models.domain import OrderType
from src.utils.fees import MAKER_FEE_PCT, TAKER_FEE_PCT, calculate_fee


class TestFeeConstants:
    def test_taker_fee_pct_constant(self):
        assert Decimal("0.0009") == TAKER_FEE_PCT

    def test_maker_fee_pct_constant(self):
        assert Decimal("0") == MAKER_FEE_PCT

    def test_taker_fee_pct_is_decimal(self):
        assert isinstance(TAKER_FEE_PCT, Decimal)

    def test_maker_fee_pct_is_decimal(self):
        assert isinstance(MAKER_FEE_PCT, Decimal)


class TestCalculateFee:
    def test_market_order_fee_is_taker_rate(self):
        fee = calculate_fee(Decimal("1000"), OrderType.MARKET)
        assert fee == Decimal("0.9")

    def test_limit_order_fee_is_zero(self):
        fee = calculate_fee(Decimal("1000"), OrderType.LIMIT)
        assert fee == Decimal("0")

    def test_fee_result_is_decimal(self):
        fee = calculate_fee(Decimal("1000"), OrderType.MARKET)
        assert isinstance(fee, Decimal)

    def test_limit_fee_result_is_decimal(self):
        fee = calculate_fee(Decimal("1000"), OrderType.LIMIT)
        assert isinstance(fee, Decimal)

    def test_market_order_fee_scales_with_value(self):
        fee_small = calculate_fee(Decimal("100"), OrderType.MARKET)
        fee_large = calculate_fee(Decimal("10000"), OrderType.MARKET)
        assert fee_small == Decimal("0.09")
        assert fee_large == Decimal("9")

    def test_zero_order_value_gives_zero_fee(self):
        fee = calculate_fee(Decimal("0"), OrderType.MARKET)
        assert fee == Decimal("0")

    def test_conditional_order_treated_as_taker(self):
        """CONDITIONAL and TPSL order types are not LIMIT — they use taker rate."""
        fee = calculate_fee(Decimal("1000"), OrderType.CONDITIONAL)
        assert fee == Decimal("0.9")

    def test_tpsl_order_treated_as_taker(self):
        fee = calculate_fee(Decimal("1000"), OrderType.TPSL)
        assert fee == Decimal("0.9")

    def test_precise_decimal_calculation(self):
        """Verify no floating-point rounding errors with typical BTC-EUR trade values."""
        # 0.01 BTC at 50,000 EUR = 500 EUR order value; fee = 0.45 EUR
        fee = calculate_fee(Decimal("500"), OrderType.MARKET)
        assert fee == Decimal("0.45")
