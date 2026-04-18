"""Tests for the three strategy improvements:

1. Momentum: emit signal only on EMA cross event (state machine)
2. Breakout: volume confirmation gate
3. BaseStrategy: fee-floor filter (expected_move ≥ 3 × round-trip taker fee)
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import ClassVar

import pytest

from src.models.domain import MarketData, OrderSide, Position
from src.strategies.breakout import BreakoutStrategy
from src.strategies.momentum import MomentumStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_market_data(
    price: Decimal,
    volume_24h: Decimal = Decimal("1000"),
    symbol: str = "BTC-EUR",
) -> MarketData:
    return MarketData(
        symbol=symbol,
        timestamp=datetime.now(UTC),
        bid=price - Decimal("1"),
        ask=price + Decimal("1"),
        last=price,
        volume_24h=volume_24h,
        high_24h=price + Decimal("500"),
        low_24h=price - Decimal("500"),
    )


def make_position(side: OrderSide = OrderSide.BUY, symbol: str = "BTC-EUR") -> Position:
    return Position(
        symbol=symbol,
        side=side,
        quantity=Decimal("0.1"),
        entry_price=Decimal("50000"),
        current_price=Decimal("50000"),
    )


# ---------------------------------------------------------------------------
# 1. Momentum — cross-event state machine
# ---------------------------------------------------------------------------


class TestMomentumCrossEvent:
    """Momentum signals must fire only on the bar where EMA crosses, not every subsequent bar."""

    # Large-amplitude oscillating uptrend: ~12% swings ensure EMA gap at cross > 0.54% fee floor
    _UP_TREND: ClassVar[list[int]] = [
        50000,
        56000,
        48000,
        58000,
        50000,
        62000,
        54000,
        66000,
        58000,
        70000,
        62000,
    ]
    # Large-amplitude oscillating downtrend
    _DOWN_TREND: ClassVar[list[int]] = [
        50000,
        44000,
        52000,
        42000,
        50000,
        38000,
        46000,
        34000,
        42000,
        30000,
        38000,
    ]

    @pytest.mark.asyncio
    async def test_no_duplicate_buy_on_sustained_bullish(self):
        """After a bullish cross fires BUY, subsequent bars where fast > slow must HOLD."""
        strat = MomentumStrategy(fast_period=3, slow_period=5, rsi_period=3, rsi_overbought=90.0)
        buy_signals = []
        for p in self._UP_TREND:
            sig = await strat.analyze(
                "BTC-EUR", make_market_data(Decimal(str(p))), [], Decimal("100000")
            )
            if sig and sig.signal_type == "BUY":
                buy_signals.append(sig)

        # Before fix: many BUYs (every bullish bar). After fix: exactly 1 (crossing bar only).
        assert len(buy_signals) >= 1, "Expected at least one BUY on the bullish cross"
        assert len(buy_signals) == 1, (
            f"BUY must fire only on the crossing bar, got {len(buy_signals)} signals"
        )

    @pytest.mark.asyncio
    async def test_no_duplicate_sell_on_sustained_bearish(self):
        """After a bearish cross fires SELL, subsequent bars where fast < slow must HOLD."""
        strat = MomentumStrategy(fast_period=3, slow_period=5, rsi_period=3, rsi_oversold=10.0)
        sell_signals = []
        for p in self._DOWN_TREND:
            sig = await strat.analyze(
                "BTC-EUR", make_market_data(Decimal(str(p))), [], Decimal("100000")
            )
            if sig and sig.signal_type == "SELL":
                sell_signals.append(sig)

        assert len(sell_signals) >= 1, "Expected at least one SELL on the bearish cross"
        assert len(sell_signals) == 1, (
            f"SELL must fire only on the crossing bar, got {len(sell_signals)} signals"
        )

    @pytest.mark.asyncio
    async def test_rsi_overbought_exit_still_fires_every_bar(self):
        """RSI-based exits must fire every bar regardless of the cross-event gate."""
        strat = MomentumStrategy(fast_period=3, slow_period=5, rsi_period=3, rsi_overbought=55.0)
        position = make_position(OrderSide.BUY)
        exit_signals = []
        for p in self._UP_TREND:
            sig = await strat.analyze(
                "BTC-EUR", make_market_data(Decimal(str(p))), [position], Decimal("100000")
            )
            if sig and sig.signal_type == "SELL":
                exit_signals.append(sig)

        # RSI exits are NOT gated by cross-event: must fire on every overbought bar
        assert len(exit_signals) > 1, (
            "RSI overbought exits must fire on every overbought bar, not just once"
        )

    @pytest.mark.asyncio
    async def test_buy_fires_again_on_second_bullish_cross(self):
        """A second bullish cross after an intervening bearish cross must emit a new BUY."""
        strat = MomentumStrategy(
            fast_period=3,
            slow_period=5,
            rsi_period=3,
            rsi_overbought=90.0,
            rsi_oversold=10.0,
        )
        symbol = "BTC-EUR"

        # First uptrend — drives a bullish cross and resets EMA state to bullish
        for p in self._UP_TREND:
            await strat.analyze(symbol, make_market_data(Decimal(str(p))), [], Decimal("100000"))

        # Downtrend — drives fast EMA below slow EMA (bearish state)
        for p in self._DOWN_TREND:
            await strat.analyze(symbol, make_market_data(Decimal(str(p))), [], Decimal("100000"))

        # Second uptrend — must re-fire BUY on the new bullish cross
        second_buy_signals = []
        for p in self._UP_TREND:
            sig = await strat.analyze(
                symbol, make_market_data(Decimal(str(p))), [], Decimal("100000")
            )
            if sig and sig.signal_type == "BUY":
                second_buy_signals.append(sig)

        assert len(second_buy_signals) >= 1, "BUY must re-fire on a second bullish cross"
        assert len(second_buy_signals) == 1, "Second cross must also fire exactly once"


# ---------------------------------------------------------------------------
# 2. Breakout — volume confirmation
# ---------------------------------------------------------------------------


class TestBreakoutVolumeConfirmation:
    """Breakout signals must be gated by above-average volume.

    RSI overbought is set to 200 (above the theoretical maximum of 100) so that
    RSI never blocks signals — tests can then isolate volume as the only gate.
    """

    _RSI_PERMISSIVE = 200.0  # effectively disables RSI overbought filter

    @pytest.mark.asyncio
    async def test_breakout_blocked_on_low_volume(self):
        """A price breakout with below-average volume must be suppressed."""
        strat = BreakoutStrategy(
            lookback_period=10,
            breakout_threshold=0.001,
            rsi_period=5,
            rsi_overbought=self._RSI_PERMISSIVE,
        )
        symbol = "BTC-EUR"
        base_price = Decimal("100")

        # Warm up: consistent normal volume so rolling average is well-established
        for _ in range(strat.lookback_period + strat.rsi_period + 5):
            await strat.analyze(
                symbol,
                make_market_data(base_price, volume_24h=Decimal("1000")),
                [],
                Decimal("100000"),
            )

        # Price breaks out, but volume is only 30% of average — below the 1.5× gate
        breakout_price = base_price * Decimal("1.05")
        sig = await strat.analyze(
            symbol,
            make_market_data(breakout_price, volume_24h=Decimal("300")),
            [],
            Decimal("100000"),
        )
        assert sig is None, "Breakout on low volume must be suppressed"

    @pytest.mark.asyncio
    async def test_breakout_passes_on_high_volume(self):
        """A price breakout with above-average volume must emit a signal."""
        strat = BreakoutStrategy(
            lookback_period=10,
            breakout_threshold=0.001,
            rsi_period=5,
            rsi_overbought=self._RSI_PERMISSIVE,
        )
        symbol = "BTC-EUR"
        base_price = Decimal("100")

        for _ in range(strat.lookback_period + strat.rsi_period + 5):
            await strat.analyze(
                symbol,
                make_market_data(base_price, volume_24h=Decimal("1000")),
                [],
                Decimal("100000"),
            )

        # Price breaks out with 2× average volume — above the 1.5× gate
        breakout_price = base_price * Decimal("1.05")
        sig = await strat.analyze(
            symbol,
            make_market_data(breakout_price, volume_24h=Decimal("2000")),
            [],
            Decimal("100000"),
        )
        assert sig is not None, "Breakout on high volume must emit a signal"
        assert sig.signal_type == "BUY", "Breakout on high volume must emit BUY"

    @pytest.mark.asyncio
    async def test_breakout_metadata_includes_volume_ratio(self):
        """Emitted breakout signals must carry volume_ratio in metadata for observability."""
        strat = BreakoutStrategy(
            lookback_period=10,
            breakout_threshold=0.001,
            rsi_period=5,
            rsi_overbought=self._RSI_PERMISSIVE,
        )
        symbol = "BTC-EUR"
        base_price = Decimal("100")

        for _ in range(strat.lookback_period + strat.rsi_period + 5):
            await strat.analyze(
                symbol,
                make_market_data(base_price, volume_24h=Decimal("1000")),
                [],
                Decimal("100000"),
            )

        breakout_price = base_price * Decimal("1.05")
        sig = await strat.analyze(
            symbol,
            make_market_data(breakout_price, volume_24h=Decimal("2000")),
            [],
            Decimal("100000"),
        )
        assert sig is not None
        assert "volume_ratio" in sig.metadata


# ---------------------------------------------------------------------------
# 3. Fee-floor filter (BaseStrategy._above_fee_floor)
# ---------------------------------------------------------------------------


class TestFeeFloor:
    """_above_fee_floor rejects moves too small to justify round-trip taker fees."""

    def _make_strat(self) -> MomentumStrategy:
        return MomentumStrategy(fast_period=3, slow_period=5, rsi_period=3)

    def test_tiny_move_is_below_floor(self):
        """A 0.1% expected move is below 3× round-trip (0.54%) — must return False."""
        assert not self._make_strat()._above_fee_floor(Decimal("0.001"))

    def test_exact_floor_passes(self):
        """A move exactly equal to 3× round-trip fee (0.54%) must pass."""
        # 3 × 2 × 0.0009 = 0.0054
        assert self._make_strat()._above_fee_floor(Decimal("0.0054"))

    def test_above_floor_passes(self):
        """A 1% expected move clears the fee floor."""
        assert self._make_strat()._above_fee_floor(Decimal("0.01"))

    def test_zero_move_is_below_floor(self):
        """Zero expected move must not pass the fee floor."""
        assert not self._make_strat()._above_fee_floor(Decimal("0"))

    @pytest.mark.asyncio
    async def test_momentum_buy_emits_at_crossover_with_minimum_strength(self):
        """Momentum emits BUY at EMA crossover with strength ≥ 0.7 regardless of gap size.

        EMA gaps are inherently near-zero at the exact crossover bar (definition of crossover).
        The strategy must still emit a signal — the fee-floor check that blocked tiny-gap
        crossovers was incorrect because it prevented the strategy from ever trading.
        Signal strength has a 0.7 base to clear the default min-signal-strength threshold.
        """
        strat = MomentumStrategy(fast_period=3, slow_period=5, rsi_period=3, rsi_overbought=90.0)
        # Micro-oscillation around 100: EMA cross will happen with a tiny gap
        prices = [100, 100.05, 99.98, 100.06, 100.02, 100.08, 100.04, 100.10, 100.06, 100.12]
        buy_signals = []
        for p in prices:
            sig = await strat.analyze(
                "BTC-EUR",
                make_market_data(Decimal(str(p))),
                [],
                Decimal("100000"),
            )
            if sig and sig.signal_type == "BUY":
                buy_signals.append(sig)

        assert buy_signals, "Momentum must emit BUY on an EMA crossover"
        for sig in buy_signals:
            assert sig.strength >= 0.7, (
                f"BUY signal strength {sig.strength:.3f} must be ≥ 0.7 to clear min-signal-strength"
            )
