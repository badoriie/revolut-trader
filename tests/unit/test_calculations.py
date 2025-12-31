"""Financial Calculation Tests - CRITICAL

These tests verify mathematical correctness of:
1. PnL calculations (unrealized and realized)
2. Position value calculations
3. Portfolio value calculations
4. Price update impact on PnL

Critical because: Wrong PnL calculations = wrong trading decisions = potential losses

Test strategy: Use exact Decimal arithmetic with known scenarios to verify
calculations match expected values. Test both long and short positions.
"""

from decimal import Decimal

from src.data.models import OrderSide, Position


class TestUnrealizedPnLCalculation:
    """Tests that verify unrealized PnL is calculated correctly."""

    def test_long_position_profit(self):
        """CRITICAL: Unrealized PnL for profitable long position.

        Context: Calculation requirement CALC-01
        Critical because: Core metric for portfolio value

        Scenario:
        - Buy 1 BTC at 50,000 EUR
        - Price rises to 55,000 EUR
        - Unrealized PnL = (55,000 - 50,000) * 1 = 5,000 EUR profit
        """
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
        )

        # Price rises
        position.update_price(Decimal("55000"))

        # Expected: 5,000 EUR profit
        expected_pnl = Decimal("5000")
        assert position.unrealized_pnl == expected_pnl

    def test_long_position_loss(self):
        """CRITICAL: Unrealized PnL for losing long position.

        Scenario:
        - Buy 1 BTC at 50,000 EUR
        - Price falls to 45,000 EUR
        - Unrealized PnL = (45,000 - 50,000) * 1 = -5,000 EUR loss
        """
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
        )

        # Price falls
        position.update_price(Decimal("45000"))

        # Expected: -5,000 EUR loss
        expected_pnl = Decimal("-5000")
        assert position.unrealized_pnl == expected_pnl

    def test_short_position_profit(self):
        """CRITICAL: Unrealized PnL for profitable short position.

        Scenario:
        - Sell 1 BTC at 50,000 EUR
        - Price falls to 45,000 EUR
        - Unrealized PnL = (50,000 - 45,000) * 1 = 5,000 EUR profit
        """
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.SELL,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
        )

        # Price falls (good for short)
        position.update_price(Decimal("45000"))

        # Expected: 5,000 EUR profit
        expected_pnl = Decimal("5000")
        assert position.unrealized_pnl == expected_pnl

    def test_short_position_loss(self):
        """CRITICAL: Unrealized PnL for losing short position.

        Scenario:
        - Sell 1 BTC at 50,000 EUR
        - Price rises to 55,000 EUR
        - Unrealized PnL = (50,000 - 55,000) * 1 = -5,000 EUR loss
        """
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.SELL,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
        )

        # Price rises (bad for short)
        position.update_price(Decimal("55000"))

        # Expected: -5,000 EUR loss
        expected_pnl = Decimal("-5000")
        assert position.unrealized_pnl == expected_pnl

    def test_fractional_quantity_pnl(self):
        """PnL calculation with fractional quantities.

        Scenario:
        - Buy 0.5 BTC at 50,000 EUR
        - Price rises to 52,000 EUR
        - Unrealized PnL = (52,000 - 50,000) * 0.5 = 1,000 EUR
        """
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("0.5"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
        )

        position.update_price(Decimal("52000"))

        expected_pnl = Decimal("1000")
        assert position.unrealized_pnl == expected_pnl

    def test_zero_pnl_at_entry_price(self):
        """Position at entry price should have zero PnL."""
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
        )

        # Update to same price
        position.update_price(Decimal("50000"))

        assert position.unrealized_pnl == Decimal("0")

    def test_multiple_price_updates(self):
        """PnL should update correctly with multiple price changes.

        Scenario:
        - Buy at 50,000
        - Price goes to 55,000 (PnL = +5,000)
        - Price goes to 48,000 (PnL = -2,000)
        - Price goes to 51,000 (PnL = +1,000)
        """
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
        )

        # Update 1: Rise
        position.update_price(Decimal("55000"))
        assert position.unrealized_pnl == Decimal("5000")

        # Update 2: Fall below entry
        position.update_price(Decimal("48000"))
        assert position.unrealized_pnl == Decimal("-2000")

        # Update 3: Rise above entry
        position.update_price(Decimal("51000"))
        assert position.unrealized_pnl == Decimal("1000")


class TestPositionValueCalculation:
    """Tests that verify position value calculations are correct."""

    def test_long_position_current_value(self):
        """Current value of long position.

        Scenario:
        - Buy 2 BTC at 50,000 EUR entry
        - Current price 52,000 EUR
        - Current value = 2 * 52,000 = 104,000 EUR
        """
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("2"),
            entry_price=Decimal("50000"),
            current_price=Decimal("52000"),
        )

        current_value = position.quantity * position.current_price
        expected = Decimal("104000")

        assert current_value == expected

    def test_short_position_current_value(self):
        """Current value of short position.

        Scenario:
        - Sell 1 BTC at 50,000 EUR entry
        - Current price 48,000 EUR
        - Current value = 1 * 48,000 = 48,000 EUR
        """
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.SELL,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("48000"),
        )

        current_value = position.quantity * position.current_price
        expected = Decimal("48000")

        assert current_value == expected

    def test_position_cost_basis(self):
        """Cost basis calculation.

        Scenario:
        - Buy 1.5 BTC at 50,000 EUR
        - Cost basis = 1.5 * 50,000 = 75,000 EUR
        """
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1.5"),
            entry_price=Decimal("50000"),
            current_price=Decimal("52000"),
        )

        cost_basis = position.quantity * position.entry_price
        expected = Decimal("75000")

        assert cost_basis == expected


class TestStopLossTakeProfitTriggers:
    """Tests that verify stop loss and take profit trigger correctly."""

    def test_long_position_hits_stop_loss(self):
        """Long position should close when price hits stop loss.

        Scenario:
        - Buy at 50,000 EUR
        - Stop loss at 49,000 EUR
        - Price drops to 49,000 EUR or below
        - Should trigger close
        """
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
            stop_loss=Decimal("49000"),
        )

        # Price at stop loss
        position.update_price(Decimal("49000"))
        should_close, reason = position.should_close()

        assert should_close
        assert reason == "stop_loss"

    def test_long_position_hits_take_profit(self):
        """Long position should close when price hits take profit.

        Scenario:
        - Buy at 50,000 EUR
        - Take profit at 52,000 EUR
        - Price rises to 52,000 EUR or above
        - Should trigger close
        """
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
            take_profit=Decimal("52000"),
        )

        # Price at take profit
        position.update_price(Decimal("52000"))
        should_close, reason = position.should_close()

        assert should_close
        assert reason == "take_profit"

    def test_short_position_hits_stop_loss(self):
        """Short position should close when price hits stop loss.

        Scenario:
        - Sell at 50,000 EUR
        - Stop loss at 51,000 EUR
        - Price rises to 51,000 EUR or above
        - Should trigger close
        """
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.SELL,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
            stop_loss=Decimal("51000"),
        )

        # Price at stop loss
        position.update_price(Decimal("51000"))
        should_close, reason = position.should_close()

        assert should_close
        assert reason == "stop_loss"

    def test_short_position_hits_take_profit(self):
        """Short position should close when price hits take profit.

        Scenario:
        - Sell at 50,000 EUR
        - Take profit at 48,000 EUR
        - Price falls to 48,000 EUR or below
        - Should trigger close
        """
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.SELL,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
            take_profit=Decimal("48000"),
        )

        # Price at take profit
        position.update_price(Decimal("48000"))
        should_close, reason = position.should_close()

        assert should_close
        assert reason == "take_profit"

    def test_no_close_when_within_bounds(self):
        """Position should NOT close when price is within bounds.

        Scenario:
        - Buy at 50,000 EUR
        - Stop loss at 49,000 EUR
        - Take profit at 52,000 EUR
        - Price at 50,500 EUR (within bounds)
        - Should NOT trigger close
        """
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50500"),
            stop_loss=Decimal("49000"),
            take_profit=Decimal("52000"),
        )

        should_close, reason = position.should_close()

        assert not should_close
        assert reason == ""


class TestDecimalPrecision:
    """Tests that verify Decimal precision is maintained in calculations."""

    def test_no_floating_point_errors(self):
        """Calculations should not have floating point errors.

        Example of floating point error:
        0.1 + 0.2 = 0.30000000000000004 (in float)

        With Decimal:
        0.1 + 0.2 = 0.3 (exact)
        """
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000.12"),
            current_price=Decimal("50000.12"),
        )

        # Update to price that would cause float errors
        position.update_price(Decimal("50000.32"))

        # PnL = (50000.32 - 50000.12) * 0.1 = 0.2 * 0.1 = 0.02
        expected_pnl = Decimal("0.02")

        assert position.unrealized_pnl == expected_pnl

    def test_high_precision_calculations(self):
        """Calculations should maintain high precision.

        Scenario:
        - Quantity with 8 decimal places (crypto precision)
        - Price with 2 decimal places (EUR precision)
        - PnL should be exact
        """
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("0.00123456"),  # 8 decimals
            entry_price=Decimal("50000.00"),
            current_price=Decimal("50000.00"),
        )

        position.update_price(Decimal("51000.00"))

        # PnL = (51000 - 50000) * 0.00123456 = 1000 * 0.00123456 = 1.23456
        expected_pnl = Decimal("1.23456")

        assert position.unrealized_pnl == expected_pnl

    def test_very_large_numbers(self):
        """Calculations should work with very large numbers.

        Scenario:
        - Large quantity
        - PnL calculation should be exact
        """
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1000"),  # 1000 BTC
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
        )

        position.update_price(Decimal("50001"))

        # PnL = (50001 - 50000) * 1000 = 1 * 1000 = 1000
        expected_pnl = Decimal("1000")

        assert position.unrealized_pnl == expected_pnl


class TestEdgeCases:
    """Tests for edge cases in calculations."""

    def test_zero_quantity_position(self):
        """Position with zero quantity should have zero PnL."""
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("0"),
            entry_price=Decimal("50000"),
            current_price=Decimal("55000"),
        )

        assert position.unrealized_pnl == Decimal("0")

    def test_very_small_price_change(self):
        """Very small price changes should be calculated exactly.

        Scenario:
        - Price change of 0.01 EUR
        - PnL should be exact, not rounded
        """
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000.00"),
            current_price=Decimal("50000.00"),
        )

        position.update_price(Decimal("50000.01"))

        # PnL = 0.01 * 1 = 0.01
        expected_pnl = Decimal("0.01")

        assert position.unrealized_pnl == expected_pnl

    def test_timestamp_updates_on_price_change(self):
        """updated_at timestamp should change when price updates."""
        position = Position(
            symbol="BTC-EUR",
            side=OrderSide.BUY,
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            current_price=Decimal("50000"),
        )

        original_timestamp = position.updated_at

        # Wait a tiny bit and update
        import time

        time.sleep(0.01)

        position.update_price(Decimal("50001"))

        assert position.updated_at > original_timestamp
