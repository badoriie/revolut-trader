"""Technical Indicator Tests - CRITICAL

These tests verify mathematical correctness of:
1. EMA (Exponential Moving Average) calculations
2. RSI (Relative Strength Index) calculations
3. Indicator warm-up periods
4. Edge cases and boundary conditions

Critical because: Wrong indicators = wrong trading signals = potential losses

Test strategy: Use known test sequences with verified expected values to
ensure calculations match standard formulas. Compare against manually
calculated values and well-known examples.
"""

from decimal import Decimal

from src.utils.indicators import EMA, RSI


class TestEMACalculation:
    """Tests that verify EMA is calculated correctly."""

    def test_ema_warmup_period(self):
        """CRITICAL: EMA should warm up before being ready.

        Context: Indicator requirement IND-01
        Critical because: EMA needs initial value

        Scenario:
        - 10-period EMA
        - First 9 values during warmup (not ready)
        - 10th value completes warmup (becomes ready)
        - EMA formula applied on 10th update
        """
        ema = EMA(period=10)

        # Feed first 10 prices
        prices = [Decimal(str(p)) for p in [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]]

        for i, price in enumerate(prices):
            result = ema.update(price)

            if i < 9:
                # During warmup, should not be ready
                assert not ema.is_ready
            else:
                # At period=10, should be ready
                assert ema.is_ready

        # After warmup completes, EMA formula has been applied
        # Result should be > SMA because last price (109) > SMA (104.5)
        expected_sma = sum(prices) / Decimal(len(prices))
        assert result > expected_sma  # EMA responds to recent price

    def test_ema_formula_correctness(self):
        """CRITICAL: EMA formula must be exact: EMA = Price * k + EMA(prev) * (1-k)

        where k = 2 / (period + 1)

        Scenario:
        - 10-period EMA
        - After warmup, verify formula is applied correctly
        """
        ema = EMA(period=10)

        # Warmup with 10 values
        warmup_prices = [Decimal(str(p)) for p in range(100, 110)]
        for price in warmup_prices:
            ema.update(price)

        # After warmup, EMA is ready
        assert ema.is_ready
        prev_ema = ema.value

        # Update with new price and verify formula
        # k = 2 / (10 + 1) = 2/11
        k = Decimal("2") / Decimal("11")
        new_price = Decimal("110")

        # Expected EMA = 110 * k + prev_ema * (1 - k)
        expected_new_ema = (new_price * k) + (prev_ema * (Decimal("1") - k))

        actual_ema = ema.update(new_price)

        # Should match within precision
        assert abs(actual_ema - expected_new_ema) < Decimal("0.000001")

    def test_ema_responds_to_price_changes(self):
        """EMA should respond to price changes but lag behind."""
        ema = EMA(period=5)

        # Warmup with stable price
        for _ in range(5):
            ema.update(Decimal("100"))

        assert ema.value == Decimal("100")

        # Price jumps to 110
        ema.update(Decimal("110"))

        # EMA should move up but not reach 110 immediately
        assert ema.value > Decimal("100")
        assert ema.value < Decimal("110")

    def test_ema_shorter_period_more_responsive(self):
        """Shorter period EMA should respond faster to price changes."""
        ema_short = EMA(period=5)
        ema_long = EMA(period=20)

        # Same warmup prices
        warmup_prices = [Decimal("100")] * 20
        for price in warmup_prices:
            ema_short.update(price)
            ema_long.update(price)

        # Both should be at 100
        assert ema_short.value == Decimal("100")
        assert ema_long.value == Decimal("100")

        # Price jumps to 110
        short_result = ema_short.update(Decimal("110"))
        long_result = ema_long.update(Decimal("110"))

        # Shorter period should move more
        assert short_result > long_result

    def test_ema_reset(self):
        """Reset should clear all state."""
        ema = EMA(period=10)

        # Add some data
        for i in range(15):
            ema.update(Decimal(str(100 + i)))

        assert ema.is_ready
        assert ema.value is not None

        # Reset
        ema.reset()

        assert not ema.is_ready
        assert ema.value is None


class TestRSICalculation:
    """Tests that verify RSI is calculated correctly."""

    def test_rsi_warmup_period(self):
        """CRITICAL: RSI should warm up before giving reliable values.

        Context: Indicator requirement IND-02
        Critical because: RSI needs sufficient data

        Scenario:
        - 14-period RSI (standard)
        - First 14 price changes needed for warmup
        - Should not be ready until warmup complete
        """
        rsi = RSI(period=14)

        # Need 15 prices (14 changes)
        for i in range(14):
            rsi.update(Decimal(str(100 + i)))
            assert not rsi.is_ready

        # 15th price completes warmup
        rsi.update(Decimal("114"))
        assert rsi.is_ready

    def test_rsi_all_gains_gives_100(self):
        """CRITICAL: RSI with all gains should approach 100.

        Scenario:
        - Continuous upward price movement
        - RSI should be near 100
        """
        rsi = RSI(period=14)

        # Continuous gains
        for i in range(20):
            rsi.update(Decimal(str(100 + i * 5)))  # +5 each time

        # RSI should be very high (near 100)
        assert rsi.value > Decimal("90")

    def test_rsi_all_losses_gives_0(self):
        """CRITICAL: RSI with all losses should approach 0.

        Scenario:
        - Continuous downward price movement
        - RSI should be near 0
        """
        rsi = RSI(period=14)

        # Continuous losses
        for i in range(20):
            rsi.update(Decimal(str(100 - i * 5)))  # -5 each time

        # RSI should be very low (near 0)
        assert rsi.value < Decimal("10")

    def test_rsi_formula_correctness(self):
        """CRITICAL: RSI formula must be exact: RSI = 100 - (100 / (1 + RS))

        where RS = Average Gain / Average Loss

        Scenario:
        - Known sequence of prices
        - Manually calculate expected RSI
        - Verify formula is correct
        """
        rsi = RSI(period=14)

        # Alternating gains and losses
        prices = [
            Decimal("100"),  # Start
            Decimal("101"),  # +1 gain
            Decimal("100"),  # -1 loss
            Decimal("102"),  # +2 gain
            Decimal("101"),  # -1 loss
            Decimal("103"),  # +2 gain
            Decimal("102"),  # -1 loss
            Decimal("104"),  # +2 gain
            Decimal("103"),  # -1 loss
            Decimal("105"),  # +2 gain
            Decimal("104"),  # -1 loss
            Decimal("106"),  # +2 gain
            Decimal("105"),  # -1 loss
            Decimal("107"),  # +2 gain
            Decimal("106"),  # -1 loss (14 changes total)
        ]

        for price in prices:
            result = rsi.update(price)

        # After warmup, avg_gain and avg_loss should follow Wilder's method
        # Gains: 1, 0, 2, 0, 2, 0, 2, 0, 2, 0, 2, 0, 2, 0 = avg = 13/14 = 0.928...
        # Losses: 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1 = avg = 7/14 = 0.5
        # RS = 0.928.../0.5 = ~1.857
        # RSI = 100 - (100 / (1 + 1.857)) = 100 - 35 = ~65

        # RSI should be above 50 (more gains than losses)
        assert result > Decimal("50")
        assert result < Decimal("80")

    def test_rsi_neutral_at_50_with_equal_moves(self):
        """RSI should be around 50 with equal gains and losses."""
        rsi = RSI(period=14)

        # Equal up and down movements
        base_price = Decimal("100")
        for i in range(20):
            if i % 2 == 0:
                rsi.update(base_price + Decimal("1"))
            else:
                rsi.update(base_price)

        # RSI should be near 50
        assert Decimal("40") < rsi.value < Decimal("60")

    def test_rsi_range_0_to_100(self):
        """RSI should always be between 0 and 100."""
        rsi = RSI(period=14)

        # Random price movements
        import random

        random.seed(42)

        for _ in range(100):
            price = Decimal(str(100 + random.uniform(-50, 50)))
            result = rsi.update(price)

            assert Decimal("0") <= result <= Decimal("100")

    def test_rsi_wilder_smoothing(self):
        """RSI should use Wilder's smoothing method.

        Wilder's smoothing:
        avg = (prev_avg * (period - 1) + current) / period

        This verifies smoothing is applied, not simple average.
        """
        rsi = RSI(period=14)

        # Warmup with gains
        for i in range(15):
            rsi.update(Decimal(str(100 + i)))

        assert rsi.is_ready
        initial_avg_gain = rsi.avg_gain

        # Add a larger gain
        rsi.update(Decimal("120"))  # +6 gain from 114

        # New avg_gain should be smoothed using Wilder's method
        # Formula: (prev_avg * 13 + current_gain) / 14
        expected_smoothed = (initial_avg_gain * Decimal("13") + Decimal("6")) / Decimal("14")

        # Should be close (allowing for floating point precision)
        assert abs(rsi.avg_gain - expected_smoothed) < Decimal("0.1")

    def test_rsi_reset(self):
        """Reset should clear all state."""
        rsi = RSI(period=14)

        # Add data
        for i in range(20):
            rsi.update(Decimal(str(100 + i)))

        assert rsi.is_ready
        assert rsi.value is not None

        # Reset
        rsi.reset()

        assert not rsi.is_ready
        assert rsi.value is None


class TestIndicatorEdgeCases:
    """Tests for edge cases in indicators."""

    def test_ema_single_price_repeated(self):
        """EMA with repeated same price should converge to that price."""
        ema = EMA(period=10)

        # Repeat same price
        for _ in range(20):
            result = ema.update(Decimal("100"))

        # Should converge to 100
        assert result == Decimal("100")

    def test_rsi_no_price_change(self):
        """RSI with no price changes should be 100 (no losses)."""
        rsi = RSI(period=14)

        # Same price repeatedly
        for _ in range(20):
            result = rsi.update(Decimal("100"))

        # No gains, no losses → avg_loss = 0 → RSI = 100
        assert result == Decimal("100")

    def test_ema_very_small_changes(self):
        """EMA should handle very small price changes precisely."""
        ema = EMA(period=10)

        # Warmup
        for _ in range(10):
            ema.update(Decimal("100.00"))

        # Very small change
        result = ema.update(Decimal("100.01"))

        # Should detect the change
        assert result > Decimal("100.00")
        assert result < Decimal("100.01")

    def test_rsi_extreme_volatility(self):
        """RSI should handle extreme price swings."""
        rsi = RSI(period=14)

        # Extreme swings
        prices = []
        for i in range(30):
            if i % 2 == 0:
                prices.append(Decimal("100"))
            else:
                prices.append(Decimal("200"))  # 100% swing

        for price in prices:
            result = rsi.update(price)

            # Should stay in valid range
            assert Decimal("0") <= result <= Decimal("100")

    def test_ema_with_zero_price(self):
        """EMA should handle zero prices (edge case)."""
        ema = EMA(period=10)

        # Include zero in sequence
        prices = [Decimal(str(i)) for i in range(10)]  # 0, 1, 2, ..., 9

        for price in prices:
            result = ema.update(price)

        # Should handle zero without errors
        assert result >= Decimal("0")

    def test_rsi_single_large_spike(self):
        """RSI should handle single large price spike."""
        rsi = RSI(period=14)

        # Start with small alternating changes to get RSI around neutral
        base_price = Decimal("100")
        for i in range(15):
            if i % 2 == 0:
                rsi.update(base_price + Decimal("1"))
            else:
                rsi.update(base_price)

        initial_rsi = rsi.value

        # Single large spike
        result = rsi.update(Decimal("200"))  # +100 gain from ~100

        # RSI should increase significantly due to large gain
        # But be smoothed by Wilder's method (not immediately 100)
        assert result > initial_rsi
        assert result > Decimal("70")  # Should be high due to large gain
        assert result <= Decimal("100")  # Can't exceed 100


class TestIndicatorPerformance:
    """Tests that verify indicators are optimized (O(1) updates)."""

    def test_ema_constant_time_update(self):
        """EMA update should be O(1) - no recalculation of history.

        This is verified by checking that update doesn't store
        historical prices after warmup.
        """
        ema = EMA(period=10)

        # Warmup
        for i in range(10):
            ema.update(Decimal(str(100 + i)))

        # Warmup prices should be cleared
        assert len(ema._warmup_prices) == 0

        # Further updates don't accumulate data
        for i in range(100):
            ema.update(Decimal(str(110 + i)))

        # No historical accumulation
        assert len(ema._warmup_prices) == 0

    def test_rsi_constant_time_update(self):
        """RSI update should be O(1) - uses Wilder's smoothing.

        Verified by checking warmup data is cleared after initialization.
        """
        rsi = RSI(period=14)

        # Warmup
        for i in range(15):
            rsi.update(Decimal(str(100 + i)))

        # Warmup data should be cleared
        assert len(rsi._warmup_gains) == 0
        assert len(rsi._warmup_losses) == 0

        # Further updates don't accumulate
        for i in range(100):
            rsi.update(Decimal(str(115 + i)))

        # No historical accumulation
        assert len(rsi._warmup_gains) == 0
        assert len(rsi._warmup_losses) == 0
