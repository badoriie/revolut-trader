"""Unit tests for data models.

Covers the uncovered property accessors in BalanceData and CandleData,
plus Position helper methods.
"""

from decimal import Decimal

from src.models.domain import (
    BalanceData,
    CandleData,
    OrderSide,
    Position,
)

# ---------------------------------------------------------------------------
# BalanceData
# ---------------------------------------------------------------------------


class TestBalanceData:
    """Tests for BalanceData property accessors."""

    def test_available_property(self):
        balance = BalanceData(availableBalance="1000.50")
        assert balance.available == Decimal("1000.50")

    def test_total_property_when_total_balance_present(self):
        balance = BalanceData(availableBalance="1000.00", totalBalance="1500.00")
        assert balance.total == Decimal("1500.00")

    def test_total_property_falls_back_to_available_when_no_total(self):
        balance = BalanceData(availableBalance="750.25")
        assert balance.total == Decimal("750.25")

    def test_available_and_total_with_zero_values(self):
        balance = BalanceData(availableBalance="0", totalBalance="0")
        assert balance.available == Decimal("0")
        assert balance.total == Decimal("0")


# ---------------------------------------------------------------------------
# CandleData
# ---------------------------------------------------------------------------


class TestCandleData:
    """Tests for CandleData property accessors."""

    def _make_candle(self, **overrides) -> CandleData:
        defaults = {
            "start": 1_700_000_000,
            "open": "50000",
            "high": "51000",
            "low": "49000",
            "close": "50500",
            "volume": "1.5",
        }
        defaults.update(overrides)
        return CandleData(**defaults)

    def test_timestamp_property(self):
        candle = self._make_candle(start=1_700_000_000)
        assert candle.timestamp == 1_700_000_000

    def test_open_price_property(self):
        candle = self._make_candle(open="50000.50")
        assert candle.open_price == Decimal("50000.50")

    def test_high_price_property(self):
        candle = self._make_candle(high="51000.75")
        assert candle.high_price == Decimal("51000.75")

    def test_low_price_property(self):
        candle = self._make_candle(low="49000.25")
        assert candle.low_price == Decimal("49000.25")

    def test_close_price_property(self):
        candle = self._make_candle(close="50500.10")
        assert candle.close_price == Decimal("50500.10")

    def test_volume_decimal_property(self):
        candle = self._make_candle(volume="2.75")
        assert candle.volume_decimal == Decimal("2.75")

    def test_float_values_are_accepted(self):
        """API may return float values — they should be converted correctly."""
        candle = CandleData(
            start=1_700_000_000,
            open=50000.0,
            high=51000.0,
            low=49000.0,
            close=50500.0,
            volume=1.5,
        )
        assert candle.open_price == Decimal("50000.0")
        assert candle.high_price == Decimal("51000.0")
        assert candle.low_price == Decimal("49000.0")
        assert candle.close_price == Decimal("50500.0")
        assert candle.volume_decimal == Decimal("1.5")


# ---------------------------------------------------------------------------
# Position helper methods
# ---------------------------------------------------------------------------


class TestPositionUpdatePrice:
    """Tests for Position.update_price()."""

    def test_update_price_long_position_positive_pnl(self):
        pos = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
        )
        pos.update_price(Decimal("52000"))
        assert pos.current_price == Decimal("52000")
        assert pos.unrealized_pnl == Decimal("2000")

    def test_update_price_long_position_negative_pnl(self):
        pos = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
        )
        pos.update_price(Decimal("48000"))
        assert pos.unrealized_pnl == Decimal("-2000")

    def test_update_price_short_position(self):
        pos = Position(
            symbol="BTC-EUR",
            side=OrderSide.SELL,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
        )
        pos.update_price(Decimal("48000"))
        # Profit for short when price falls
        assert pos.unrealized_pnl == Decimal("2000")


class TestPositionShouldClose:
    """Tests for Position.should_close()."""

    def test_should_close_on_stop_loss(self):
        pos = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("48000"),
            stop_loss=Decimal("49000"),
        )
        should_close, reason = pos.should_close()
        assert should_close is True
        assert reason == "stop_loss"

    def test_should_close_on_take_profit(self):
        pos = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("52000"),
            take_profit=Decimal("51500"),
        )
        should_close, reason = pos.should_close()
        assert should_close is True
        assert reason == "take_profit"

    def test_should_not_close_when_within_range(self):
        pos = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50500"),
            stop_loss=Decimal("49000"),
            take_profit=Decimal("52000"),
        )
        should_close, reason = pos.should_close()
        assert should_close is False
        assert reason == ""

    def test_should_not_close_when_no_stop_or_tp(self):
        pos = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
        )
        should_close, reason = pos.should_close()
        assert should_close is False
        assert reason == ""
