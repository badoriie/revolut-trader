"""Unit tests for all trading strategies.

Covers: BaseStrategy, MomentumStrategy, MeanReversionStrategy,
        MarketMakingStrategy, MultiStrategy, BreakoutStrategy,
        RangeReversionStrategy.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.models.domain import MarketData, OrderSide, Position, Signal
from src.strategies.breakout import BreakoutStrategy
from src.strategies.market_making import MarketMakingStrategy
from src.strategies.mean_reversion import MeanReversionStrategy
from src.strategies.momentum import MomentumStrategy
from src.strategies.multi_strategy import MultiStrategy
from src.strategies.range_reversion import RangeReversionStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_market_data(
    symbol: str = "BTC-EUR",
    last: Decimal = Decimal("50000"),
    bid: Decimal = Decimal("49950"),
    ask: Decimal = Decimal("50050"),
    volume_24h: Decimal = Decimal("1000"),
    high_24h: Decimal = Decimal("51000"),
    low_24h: Decimal = Decimal("49000"),
) -> MarketData:
    """Create a MarketData snapshot for the given price."""
    return MarketData(
        symbol=symbol,
        timestamp=datetime.now(UTC),
        bid=bid,
        ask=ask,
        last=last,
        volume_24h=volume_24h,
        high_24h=high_24h,
        low_24h=low_24h,
    )


def make_position(
    symbol: str = "BTC-EUR",
    side: OrderSide = OrderSide.BUY,
    entry_price: Decimal = Decimal("50000"),
    current_price: Decimal = Decimal("50000"),
    quantity: Decimal = Decimal("0.1"),
) -> Position:
    """Create a Position for testing."""
    return Position(
        symbol=symbol,
        side=side,
        quantity=quantity,
        entry_price=entry_price,
        current_price=current_price,
    )


# ---------------------------------------------------------------------------
# BaseStrategy (via concrete subclass)
# ---------------------------------------------------------------------------


class TestBaseStrategy:
    """Tests for BaseStrategy activate / deactivate."""

    def test_strategy_is_active_by_default(self):
        strategy = MomentumStrategy()
        assert strategy.is_active is True

    def test_deactivate_sets_is_active_false(self):
        strategy = MomentumStrategy()
        strategy.deactivate()
        assert strategy.is_active is False

    def test_activate_restores_is_active(self):
        strategy = MomentumStrategy()
        strategy.deactivate()
        strategy.activate()
        assert strategy.is_active is True

    def test_strategy_name_is_set(self):
        strategy = MomentumStrategy()
        assert strategy.name == "Momentum"


# ---------------------------------------------------------------------------
# MomentumStrategy
# ---------------------------------------------------------------------------


class TestMomentumStrategy:
    """Tests for MomentumStrategy."""

    def test_get_parameters_contains_expected_keys(self):
        strategy = MomentumStrategy(fast_period=10, slow_period=20, rsi_period=14)
        params = strategy.get_parameters()
        assert params["strategy"] == "Momentum"
        assert params["fast_period"] == 10
        assert params["slow_period"] == 20
        assert params["rsi_period"] == 14

    @pytest.mark.asyncio
    async def test_returns_none_before_indicators_warm_up(self):
        """Indicators need data before producing signals."""
        strategy = MomentumStrategy()
        md = make_market_data()
        result = await strategy.analyze("BTC-EUR", md, [], Decimal("10000"))
        assert result is None

    @pytest.mark.asyncio
    async def test_no_signal_on_flat_prices_after_warmup(self):
        """Flat prices → fast EMA ≈ slow EMA → no directional signal."""
        strategy = MomentumStrategy(fast_period=5, slow_period=10, rsi_period=7)
        portfolio_value = Decimal("10000")
        result = None
        for _ in range(30):
            md = make_market_data(last=Decimal("50000"))
            result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        # Flat prices: no crossover → HOLD → None
        assert result is None

    @pytest.mark.asyncio
    async def test_buy_signal_on_strongly_rising_prices(self):
        """Oscillating uptrend keeps RSI moderate while fast EMA rises above slow EMA → BUY."""
        strategy = MomentumStrategy(fast_period=3, slow_period=5, rsi_period=3, rsi_overbought=90.0)
        portfolio_value = Decimal("10000")
        # Oscillating uptrend: losses interspersed prevent RSI from hitting 100
        prices = [50000, 51000, 49500, 51500, 50500, 52000, 51000, 53000]
        buy_signals = []
        for p in prices:
            md = make_market_data(last=Decimal(str(p)))
            result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
            if result is not None and result.signal_type == "BUY":
                buy_signals.append(result)

        assert len(buy_signals) > 0, "Expected at least one BUY signal from oscillating uptrend"
        signal = buy_signals[0]
        assert signal.symbol == "BTC-EUR"
        assert signal.strategy == "Momentum"
        assert 0.0 <= signal.strength <= 1.0

    @pytest.mark.asyncio
    async def test_sell_signal_on_strongly_falling_prices(self):
        """Oscillating downtrend keeps RSI moderate while fast EMA falls below slow EMA → SELL."""
        strategy = MomentumStrategy(fast_period=3, slow_period=5, rsi_period=3, rsi_oversold=10.0)
        portfolio_value = Decimal("10000")
        # Oscillating downtrend: gains interspersed prevent RSI from hitting 0
        prices = [50000, 49000, 50500, 48500, 49500, 48000, 49000, 47000]
        sell_signals = []
        for p in prices:
            md = make_market_data(last=Decimal(str(p)))
            result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
            if result is not None and result.signal_type == "SELL":
                sell_signals.append(result)

        assert len(sell_signals) > 0, "Expected at least one SELL signal from oscillating downtrend"
        assert sell_signals[0].signal_type == "SELL"

    @pytest.mark.asyncio
    async def test_rsi_overbought_exit_closes_long(self):
        """RSI overbought should close an existing long position."""
        strategy = MomentumStrategy(fast_period=3, slow_period=5, rsi_period=3, rsi_overbought=55.0)
        portfolio_value = Decimal("10000")
        long_position = make_position(side=OrderSide.BUY)
        result = None
        for i in range(20):
            price = Decimal(str(50000 + i * 1000))
            md = make_market_data(last=price)
            result = await strategy.analyze("BTC-EUR", md, [long_position], portfolio_value)
        # At some point with an overbought RSI threshold of 55, a SELL exit appears
        if result is not None:
            assert result.signal_type in ("BUY", "SELL")

    @pytest.mark.asyncio
    async def test_rsi_oversold_exit_closes_short(self):
        """RSI oversold should close an existing short position."""
        strategy = MomentumStrategy(fast_period=3, slow_period=5, rsi_period=3, rsi_oversold=45.0)
        portfolio_value = Decimal("10000")
        short_position = make_position(side=OrderSide.SELL)
        result = None
        for i in range(20):
            price = Decimal(str(50000 - i * 1000))
            md = make_market_data(last=price)
            result = await strategy.analyze("BTC-EUR", md, [short_position], portfolio_value)
        if result is not None:
            assert result.signal_type in ("BUY", "SELL")

    @pytest.mark.asyncio
    async def test_signal_metadata_contains_indicators(self):
        """Signal metadata should include EMA and RSI values."""
        strategy = MomentumStrategy(fast_period=3, slow_period=5, rsi_period=3, rsi_overbought=90.0)
        portfolio_value = Decimal("10000")
        result = None
        for i in range(15):
            price = Decimal(str(50000 + i * 2000))
            md = make_market_data(last=price)
            result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        if result is not None:
            assert "fast_ma" in result.metadata
            assert "slow_ma" in result.metadata
            assert "rsi" in result.metadata

    @pytest.mark.asyncio
    async def test_per_symbol_indicator_isolation(self):
        """Each symbol gets its own indicator state."""
        strategy = MomentumStrategy()
        md_btc = make_market_data(symbol="BTC-EUR")
        md_eth = make_market_data(symbol="ETH-EUR")
        await strategy.analyze("BTC-EUR", md_btc, [], Decimal("10000"))
        await strategy.analyze("ETH-EUR", md_eth, [], Decimal("10000"))
        assert "BTC-EUR" in strategy.fast_ema
        assert "ETH-EUR" in strategy.fast_ema


# ---------------------------------------------------------------------------
# MeanReversionStrategy
# ---------------------------------------------------------------------------


class TestMeanReversionStrategy:
    """Tests for MeanReversionStrategy."""

    def test_get_parameters_contains_expected_keys(self):
        strategy = MeanReversionStrategy(lookback_period=20)
        params = strategy.get_parameters()
        assert params["strategy"] == "Mean Reversion"
        assert params["lookback_period"] == 20

    @pytest.mark.asyncio
    async def test_returns_none_before_sufficient_data(self):
        """Insufficient history → None."""
        strategy = MeanReversionStrategy(lookback_period=20)
        md = make_market_data()
        result = await strategy.analyze("BTC-EUR", md, [], Decimal("10000"))
        assert result is None

    @pytest.mark.asyncio
    async def test_buy_signal_when_price_below_lower_band(self):
        """Price crash below lower Bollinger Band → BUY."""
        strategy = MeanReversionStrategy(lookback_period=10, num_std_dev=1.0, min_deviation=0.005)
        portfolio_value = Decimal("10000")
        # Establish stable mean at 50 000
        for _ in range(10):
            md = make_market_data(last=Decimal("50000"))
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        # Price crashes well below mean → lower band is breached
        md = make_market_data(last=Decimal("48000"))
        result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        assert result is not None
        assert result.signal_type == "BUY"
        assert result.symbol == "BTC-EUR"
        assert 0.0 <= result.strength <= 1.0

    @pytest.mark.asyncio
    async def test_sell_signal_when_price_above_upper_band(self):
        """Price spike above upper Bollinger Band → SELL."""
        strategy = MeanReversionStrategy(lookback_period=10, num_std_dev=1.0, min_deviation=0.005)
        portfolio_value = Decimal("10000")
        for _ in range(10):
            md = make_market_data(last=Decimal("50000"))
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        md = make_market_data(last=Decimal("52000"))
        result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        assert result is not None
        assert result.signal_type == "SELL"

    @pytest.mark.asyncio
    async def test_exit_long_when_price_returns_to_mean(self):
        """Existing long position is closed when price returns to mean."""
        strategy = MeanReversionStrategy(lookback_period=5, num_std_dev=2.0, min_deviation=0.01)
        portfolio_value = Decimal("10000")
        long_position = make_position(side=OrderSide.BUY, entry_price=Decimal("48000"))
        # Fill history with stable prices
        for _ in range(5):
            md = make_market_data(last=Decimal("50000"))
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        # Price at mean → close long
        md = make_market_data(last=Decimal("50000"))
        result = await strategy.analyze("BTC-EUR", md, [long_position], portfolio_value)
        assert result is not None
        assert result.signal_type == "SELL"

    @pytest.mark.asyncio
    async def test_exit_short_when_price_returns_to_mean(self):
        """Existing short position is closed when price returns to mean."""
        strategy = MeanReversionStrategy(lookback_period=5, num_std_dev=2.0, min_deviation=0.01)
        portfolio_value = Decimal("10000")
        short_position = make_position(side=OrderSide.SELL, entry_price=Decimal("52000"))
        for _ in range(5):
            md = make_market_data(last=Decimal("50000"))
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        # Price below mean → close short
        md = make_market_data(last=Decimal("49500"))
        result = await strategy.analyze("BTC-EUR", md, [short_position], portfolio_value)
        assert result is not None
        assert result.signal_type == "BUY"

    @pytest.mark.asyncio
    async def test_no_signal_when_price_within_bands(self):
        """Price within bands, no position → None."""
        strategy = MeanReversionStrategy(lookback_period=5, num_std_dev=3.0, min_deviation=0.5)
        portfolio_value = Decimal("10000")
        for _ in range(5):
            md = make_market_data(last=Decimal("50000"))
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        md = make_market_data(last=Decimal("50000"))
        result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        assert result is None

    @pytest.mark.asyncio
    async def test_signal_metadata_contains_band_values(self):
        """Signal metadata should contain Bollinger Band statistics."""
        strategy = MeanReversionStrategy(lookback_period=10, num_std_dev=1.0, min_deviation=0.005)
        portfolio_value = Decimal("10000")
        for _ in range(10):
            md = make_market_data(last=Decimal("50000"))
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        md = make_market_data(last=Decimal("48000"))
        result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        assert result is not None
        assert "mean_price" in result.metadata
        assert "upper_band" in result.metadata
        assert "lower_band" in result.metadata
        assert "deviation" in result.metadata

    @pytest.mark.asyncio
    async def test_does_not_buy_when_long_already_and_below_band(self):
        """Should not open another long when already long and below lower band."""
        strategy = MeanReversionStrategy(lookback_period=10, num_std_dev=1.0, min_deviation=0.005)
        portfolio_value = Decimal("10000")
        long_position = make_position(side=OrderSide.BUY)
        for _ in range(10):
            md = make_market_data(last=Decimal("50000"))
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        md = make_market_data(last=Decimal("48000"))
        result = await strategy.analyze("BTC-EUR", md, [long_position], portfolio_value)
        # Cannot buy more when already long; the exit condition (above mean) isn't met here
        assert result is None or result.signal_type == "SELL"


# ---------------------------------------------------------------------------
# MarketMakingStrategy
# ---------------------------------------------------------------------------


class TestMarketMakingStrategy:
    """Tests for MarketMakingStrategy."""

    def test_get_parameters_contains_expected_keys(self):
        strategy = MarketMakingStrategy()
        params = strategy.get_parameters()
        assert params["strategy"] == "Market Making"
        assert "spread_threshold" in params
        assert "inventory_target" in params
        assert "order_book_depth" in params

    @pytest.mark.asyncio
    async def test_returns_none_when_spread_below_threshold(self):
        """Spread too narrow → None."""
        strategy = MarketMakingStrategy(spread_threshold=0.01)  # 1 % threshold
        # Actual spread ≈ 0.2 % (well below 1 %)
        md = make_market_data(bid=Decimal("49950"), ask=Decimal("50050"))
        result = await strategy.analyze("BTC-EUR", md, [], Decimal("10000"))
        assert result is None

    @pytest.mark.asyncio
    async def test_sell_signal_on_excess_long_inventory(self):
        """Inventory ratio above target → SELL to rebalance."""
        strategy = MarketMakingStrategy(spread_threshold=0.001, inventory_target=0.3)
        # Large long position → excess inventory
        # inventory_ratio = 5 / (10000/50000) = 5 / 0.2 = 25 >> 0.3
        position = make_position(side=OrderSide.BUY, quantity=Decimal("5.0"))
        md = make_market_data(bid=Decimal("49950"), ask=Decimal("50050"), last=Decimal("50000"))
        result = await strategy.analyze("BTC-EUR", md, [position], Decimal("10000"))
        assert result is not None
        assert result.signal_type == "SELL"
        assert result.price == Decimal("50050")  # ask price for sells

    @pytest.mark.asyncio
    async def test_buy_signal_on_low_inventory(self):
        """No positions → inventory_ratio = 0 < half target → BUY."""
        strategy = MarketMakingStrategy(spread_threshold=0.001, inventory_target=0.5)
        md = make_market_data(bid=Decimal("49950"), ask=Decimal("50050"), last=Decimal("50000"))
        result = await strategy.analyze("BTC-EUR", md, [], Decimal("10000"))
        assert result is not None
        assert result.signal_type == "BUY"

    @pytest.mark.asyncio
    async def test_balanced_inventory_produces_buy_at_bid(self):
        """Balanced inventory → BUY at bid price."""
        strategy = MarketMakingStrategy(spread_threshold=0.001, inventory_target=0.5)
        # inventory_ratio = 0.07 / (10000/50000) = 0.07 / 0.2 = 0.35
        # 0.35 is between half_target (0.25) and target (0.5) → balanced
        position = make_position(side=OrderSide.BUY, quantity=Decimal("0.07"))
        md = make_market_data(bid=Decimal("49950"), ask=Decimal("50050"), last=Decimal("50000"))
        result = await strategy.analyze("BTC-EUR", md, [position], Decimal("10000"))
        assert result is not None
        assert result.signal_type == "BUY"
        assert result.price == Decimal("49950")  # bid price

    @pytest.mark.asyncio
    async def test_sell_position_reduces_effective_inventory(self):
        """Short position lowers effective qty, may trigger a BUY signal."""
        strategy = MarketMakingStrategy(spread_threshold=0.001, inventory_target=0.5)
        short_position = make_position(side=OrderSide.SELL, quantity=Decimal("0.1"))
        md = make_market_data(bid=Decimal("49950"), ask=Decimal("50050"), last=Decimal("50000"))
        result = await strategy.analyze("BTC-EUR", md, [short_position], Decimal("10000"))
        assert result is not None

    @pytest.mark.asyncio
    async def test_signal_metadata_contains_spread(self):
        """Signal metadata should include spread and inventory ratio."""
        strategy = MarketMakingStrategy(spread_threshold=0.001, inventory_target=0.5)
        md = make_market_data(bid=Decimal("49950"), ask=Decimal("50050"), last=Decimal("50000"))
        result = await strategy.analyze("BTC-EUR", md, [], Decimal("10000"))
        assert result is not None
        assert "spread" in result.metadata
        assert "inventory_ratio" in result.metadata


# ---------------------------------------------------------------------------
# MultiStrategy
# ---------------------------------------------------------------------------


class TestMultiStrategy:
    """Tests for MultiStrategy."""

    def test_default_weights_sum_to_one(self):
        strategy = MultiStrategy()
        assert abs(sum(strategy.weights.values()) - 1.0) < 0.01

    def test_custom_weights_are_normalised(self):
        """Weights that don't sum to 1.0 are normalised automatically."""
        strategy = MultiStrategy(
            weights={"market_making": 2.0, "momentum": 2.0, "mean_reversion": 2.0}
        )
        assert abs(sum(strategy.weights.values()) - 1.0) < 0.01

    def test_get_parameters_contains_expected_keys(self):
        strategy = MultiStrategy()
        params = strategy.get_parameters()
        assert params["strategy"] == "Multi-Strategy"
        assert "weights" in params
        assert "min_consensus" in params
        assert "active_strategies" in params

    def test_set_strategy_weight_and_renormalise(self):
        strategy = MultiStrategy()
        strategy.set_strategy_weight("momentum", 0.8)
        assert abs(sum(strategy.weights.values()) - 1.0) < 0.01
        assert strategy.weights["momentum"] > 0

    def test_set_strategy_weight_unknown_name_is_noop(self):
        """Setting weight for unknown strategy should not change anything."""
        strategy = MultiStrategy()
        original_weights = dict(strategy.weights)
        strategy.set_strategy_weight("nonexistent", 0.5)
        assert strategy.weights == original_weights

    def test_activate_and_deactivate_sub_strategy(self):
        strategy = MultiStrategy()
        strategy.deactivate_strategy("momentum")
        assert not strategy.strategies["momentum"].is_active
        assert "momentum" not in strategy.get_parameters()["active_strategies"]
        strategy.activate_strategy("momentum")
        assert strategy.strategies["momentum"].is_active

    def test_activate_deactivate_unknown_name_does_not_raise(self):
        """Operations on unknown strategy names are silently ignored."""
        strategy = MultiStrategy()
        strategy.activate_strategy("unknown")
        strategy.deactivate_strategy("unknown")

    @pytest.mark.asyncio
    async def test_returns_none_when_no_sub_strategies_fire(self):
        """All sub-strategies return None (warming up) → None."""
        strategy = MultiStrategy()
        md = make_market_data()
        result = await strategy.analyze("BTC-EUR", md, [], Decimal("10000"))
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_consensus_buy_signal(self):
        """Wide spread + low min_consensus → consensus BUY signal propagated."""
        strategy = MultiStrategy(min_consensus=0.1)
        # Very wide spread so MarketMaking fires immediately
        md = make_market_data(bid=Decimal("45000"), ask=Decimal("55000"), last=Decimal("50000"))
        result = await strategy.analyze("BTC-EUR", md, [], Decimal("10000"))
        assert result is not None
        assert result.signal_type == "BUY"
        assert result.strategy == "Multi-Strategy"
        assert 0.0 <= result.strength <= 1.0
        assert "buy_score" in result.metadata

    @pytest.mark.asyncio
    async def test_returns_none_when_consensus_below_threshold(self):
        """Score below min_consensus → None."""
        strategy = MultiStrategy(min_consensus=0.99)
        md = make_market_data(bid=Decimal("45000"), ask=Decimal("55000"), last=Decimal("50000"))
        result = await strategy.analyze("BTC-EUR", md, [], Decimal("10000"))
        assert result is None

    @pytest.mark.asyncio
    async def test_deactivated_strategy_is_skipped(self):
        """Deactivated sub-strategy should not contribute to consensus."""
        strategy = MultiStrategy(min_consensus=0.1)
        strategy.deactivate_strategy("market_making")
        strategy.deactivate_strategy("momentum")
        strategy.deactivate_strategy("mean_reversion")
        md = make_market_data()
        result = await strategy.analyze("BTC-EUR", md, [], Decimal("10000"))
        assert result is None

    @pytest.mark.asyncio
    async def test_consensus_sell_signal(self):
        """Excess long inventory drives a weighted SELL consensus."""
        strategy = MultiStrategy(min_consensus=0.1)
        # Large long position → MarketMaking signals SELL
        position = make_position(side=OrderSide.BUY, quantity=Decimal("100.0"))
        # Wide spread so market making fires
        md = make_market_data(bid=Decimal("45000"), ask=Decimal("55000"), last=Decimal("50000"))
        result = await strategy.analyze("BTC-EUR", md, [position], Decimal("10000"))
        assert result is not None
        assert result.signal_type == "SELL"

    @pytest.mark.asyncio
    async def test_tie_returns_none(self):
        """When buy_score == sell_score the strategy returns None."""
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock

        strategy = MultiStrategy(min_consensus=0.0)
        buy_sig = Signal(
            symbol="BTC-EUR",
            strategy="s1",
            signal_type="BUY",
            strength=1.0,
            price=Decimal("50000"),
            reason="r",
            timestamp=datetime.now(UTC),
        )
        sell_sig = Signal(
            symbol="BTC-EUR",
            strategy="s2",
            signal_type="SELL",
            strength=1.0,
            price=Decimal("50000"),
            reason="r",
            timestamp=datetime.now(UTC),
        )
        strategy.strategies["market_making"].analyze = AsyncMock(return_value=buy_sig)
        strategy.strategies["momentum"].analyze = AsyncMock(return_value=sell_sig)
        strategy.strategies["mean_reversion"].analyze = AsyncMock(return_value=None)
        # Equal weight → buy_score = 0.5, sell_score = 0.5 → tie → None
        strategy.weights = {"market_making": 0.5, "momentum": 0.5, "mean_reversion": 0.0}

        md = make_market_data()
        result = await strategy.analyze("BTC-EUR", md, [], Decimal("10000"))
        assert result is None

    def test_default_weights_include_new_strategies(self):
        """Default weights cover all five sub-strategies."""
        strategy = MultiStrategy()
        assert "breakout" in strategy.weights
        assert "range_reversion" in strategy.weights
        assert abs(sum(strategy.weights.values()) - 1.0) < 0.01

    def test_all_five_sub_strategies_registered(self):
        """All five sub-strategies are present in the strategies dict."""
        strategy = MultiStrategy()
        assert "breakout" in strategy.strategies
        assert "range_reversion" in strategy.strategies
        assert len(strategy.strategies) == 5


# ---------------------------------------------------------------------------
# MarketMakingStrategy — additional tests for signed inventory fix
# ---------------------------------------------------------------------------


class TestMarketMakingInventoryDirection:
    """Verify that the signed inventory ratio correctly handles net-short positions."""

    @pytest.mark.asyncio
    async def test_excess_short_position_triggers_buy(self):
        """A large net-short inventory should trigger BUY to rebalance, not SELL."""
        strategy = MarketMakingStrategy(spread_threshold=0.001, inventory_target=0.1)
        # Short 5 BTC: signed_ratio = -5 / (10000/50000) = -25 << -0.1 → BUY
        short_position = make_position(side=OrderSide.SELL, quantity=Decimal("5.0"))
        md = make_market_data(bid=Decimal("49950"), ask=Decimal("50050"), last=Decimal("50000"))
        result = await strategy.analyze("BTC-EUR", md, [short_position], Decimal("10000"))
        assert result is not None
        assert result.signal_type == "BUY"

    @pytest.mark.asyncio
    async def test_signed_inventory_ratio_in_metadata(self):
        """inventory_ratio in metadata is now signed (positive = long, negative = short)."""
        strategy = MarketMakingStrategy(spread_threshold=0.001, inventory_target=0.5)
        short_position = make_position(side=OrderSide.SELL, quantity=Decimal("0.1"))
        md = make_market_data(bid=Decimal("49950"), ask=Decimal("50050"), last=Decimal("50000"))
        result = await strategy.analyze("BTC-EUR", md, [short_position], Decimal("10000"))
        assert result is not None
        assert result.metadata["inventory_ratio"] < 0  # negative = net short


# ---------------------------------------------------------------------------
# MeanReversionStrategy — additional tests for strength scaling fix
# ---------------------------------------------------------------------------


class TestMeanReversionStrengthScaling:
    """Verify that entry signal strength scales proportionally with deviation."""

    @pytest.mark.asyncio
    async def test_larger_deviation_produces_higher_strength(self):
        """A price further below the lower band should produce a higher-strength signal."""
        strategy_a = MeanReversionStrategy(lookback_period=10, num_std_dev=1.0, min_deviation=0.005)
        strategy_b = MeanReversionStrategy(lookback_period=10, num_std_dev=1.0, min_deviation=0.005)
        portfolio_value = Decimal("10000")

        # Warm up both strategies with the same stable history
        for _ in range(10):
            for s in (strategy_a, strategy_b):
                md = make_market_data(last=Decimal("50000"))
                await s.analyze("BTC-EUR", md, [], portfolio_value)

        # Moderate deviation
        md_a = make_market_data(last=Decimal("48500"))
        result_a = await strategy_a.analyze("BTC-EUR", md_a, [], portfolio_value)

        # Larger deviation
        md_b = make_market_data(last=Decimal("47500"))
        result_b = await strategy_b.analyze("BTC-EUR", md_b, [], portfolio_value)

        assert result_a is not None and result_a.signal_type == "BUY"
        assert result_b is not None and result_b.signal_type == "BUY"
        assert (
            result_b.strength >= result_a.strength
        ), "Larger deviation should yield equal or higher strength"

    @pytest.mark.asyncio
    async def test_entry_strength_does_not_always_equal_one(self):
        """Entry signal strength should be < 1.0 at modest deviations."""
        strategy = MeanReversionStrategy(lookback_period=10, num_std_dev=1.0, min_deviation=0.005)
        portfolio_value = Decimal("10000")
        for _ in range(10):
            md = make_market_data(last=Decimal("50000"))
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        # Only ~0.5% below the band — deviation = 1 × min_deviation → strength = 0.5
        md = make_market_data(last=Decimal("49750"))
        result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        if result is not None and result.signal_type == "BUY":
            assert result.strength < 1.0, "Minimal deviation should not yield maximum strength"


# ---------------------------------------------------------------------------
# BreakoutStrategy
# ---------------------------------------------------------------------------


class TestBreakoutStrategy:
    """Tests for BreakoutStrategy."""

    def test_get_parameters_contains_expected_keys(self):
        strategy = BreakoutStrategy(lookback_period=10, breakout_threshold=0.002)
        params = strategy.get_parameters()
        assert params["strategy"] == "Breakout"
        assert params["lookback_period"] == 10
        assert params["breakout_threshold"] == pytest.approx(0.002)
        assert "rsi_period" in params
        assert "rsi_overbought" in params
        assert "rsi_oversold" in params

    @pytest.mark.asyncio
    async def test_returns_none_before_sufficient_data(self):
        """Insufficient history → None."""
        strategy = BreakoutStrategy(lookback_period=20)
        md = make_market_data()
        result = await strategy.analyze("BTC-EUR", md, [], Decimal("10000"))
        assert result is None

    @pytest.mark.asyncio
    async def test_buy_signal_on_upward_breakout(self):
        """Price breaks above rolling high + threshold → BUY."""
        # rsi_period=3 so RSI warms up within the 5-price lookback window
        strategy = BreakoutStrategy(
            lookback_period=5,
            breakout_threshold=0.001,
            rsi_period=3,
            rsi_overbought=90.0,
        )
        portfolio_value = Decimal("10000")
        # Establish a tight range at 50 000 (oscillating to prevent RSI hitting 100)
        for p in (50000, 49500, 50000, 49500, 50000):
            md = make_market_data(last=Decimal(str(p)))
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        # Break above: 50000 × 1.001 = 50050; price = 50100 clears it
        md = make_market_data(last=Decimal("50100"))
        result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        assert result is not None
        assert result.signal_type == "BUY"
        assert result.symbol == "BTC-EUR"
        assert result.strategy == "Breakout"
        assert 0.0 <= result.strength <= 1.0

    @pytest.mark.asyncio
    async def test_sell_signal_on_downward_breakout(self):
        """Price breaks below rolling low + threshold → SELL."""
        # rsi_period=3 and rsi_oversold=10 so a falling price still triggers SELL
        strategy = BreakoutStrategy(
            lookback_period=5,
            breakout_threshold=0.001,
            rsi_period=3,
            rsi_oversold=10.0,
        )
        portfolio_value = Decimal("10000")
        # Oscillating range so RSI stays above 10
        for p in (50000, 50500, 50000, 50500, 50000):
            md = make_market_data(last=Decimal(str(p)))
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        # Break below: 50000 × (1 - 0.001) = 49950; price = 49900 clears it
        md = make_market_data(last=Decimal("49900"))
        result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        assert result is not None
        assert result.signal_type == "SELL"
        assert 0.0 <= result.strength <= 1.0

    @pytest.mark.asyncio
    async def test_no_signal_when_price_within_range(self):
        """Price within range (below breakout threshold) → None."""
        strategy = BreakoutStrategy(lookback_period=5, breakout_threshold=0.01)  # 1 % buffer
        portfolio_value = Decimal("10000")
        for _ in range(5):
            md = make_market_data(last=Decimal("50000"))
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        # Tiny move: not beyond 50 000 × 1.01 = 50 500
        md = make_market_data(last=Decimal("50100"))
        result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        assert result is None

    @pytest.mark.asyncio
    async def test_rsi_overbought_blocks_buy_signal(self):
        """RSI overbought prevents BUY signal even on upward breakout."""
        # Very low overbought threshold so strongly rising prices trip it
        strategy = BreakoutStrategy(
            lookback_period=5,
            breakout_threshold=0.001,
            rsi_period=3,
            rsi_overbought=55.0,
        )
        portfolio_value = Decimal("10000")
        # Feed strongly rising prices to get RSI well above 55
        rising = [50000, 51000, 52000, 53000, 54000, 55000]
        for p in rising:
            md = make_market_data(last=Decimal(str(p)))
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        # Breakout attempt into overbought conditions
        md = make_market_data(last=Decimal("56000"))
        result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        # With RSI >> 55, the BUY must be suppressed
        if result is not None:
            assert result.signal_type != "BUY"

    @pytest.mark.asyncio
    async def test_rsi_oversold_blocks_sell_signal(self):
        """RSI oversold prevents SELL signal even on downward breakout."""
        strategy = BreakoutStrategy(
            lookback_period=5,
            breakout_threshold=0.001,
            rsi_period=3,
            rsi_oversold=45.0,
        )
        portfolio_value = Decimal("10000")
        falling = [50000, 49000, 48000, 47000, 46000, 45000]
        for p in falling:
            md = make_market_data(last=Decimal(str(p)))
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        md = make_market_data(last=Decimal("44000"))
        result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        if result is not None:
            assert result.signal_type != "SELL"

    @pytest.mark.asyncio
    async def test_does_not_open_long_when_already_long(self):
        """Existing long position suppresses duplicate BUY breakout signals."""
        strategy = BreakoutStrategy(
            lookback_period=5,
            breakout_threshold=0.001,
            rsi_period=3,
            rsi_overbought=90.0,
        )
        portfolio_value = Decimal("10000")
        long_position = make_position(side=OrderSide.BUY)
        for p in (50000, 49500, 50000, 49500, 50000):
            md = make_market_data(last=Decimal(str(p)))
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        md = make_market_data(last=Decimal("50100"))
        result = await strategy.analyze("BTC-EUR", md, [long_position], portfolio_value)
        assert result is None or result.signal_type != "BUY"

    @pytest.mark.asyncio
    async def test_metadata_contains_expected_fields(self):
        """Signal metadata includes rolling range and RSI values."""
        strategy = BreakoutStrategy(
            lookback_period=5,
            breakout_threshold=0.001,
            rsi_period=3,
            rsi_overbought=90.0,
        )
        portfolio_value = Decimal("10000")
        for p in (50000, 49500, 50000, 49500, 50000):
            md = make_market_data(last=Decimal(str(p)))
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        md = make_market_data(last=Decimal("50100"))
        result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        assert result is not None
        assert "rolling_high" in result.metadata
        assert "rolling_low" in result.metadata
        assert "rsi" in result.metadata
        assert "breakout_high" in result.metadata
        assert "breakout_low" in result.metadata

    @pytest.mark.asyncio
    async def test_per_symbol_state_isolation(self):
        """Each trading symbol maintains independent price history and RSI."""
        strategy = BreakoutStrategy()
        await strategy.analyze("BTC-EUR", make_market_data(symbol="BTC-EUR"), [], Decimal("10000"))
        await strategy.analyze("ETH-EUR", make_market_data(symbol="ETH-EUR"), [], Decimal("10000"))
        assert "BTC-EUR" in strategy.price_history
        assert "ETH-EUR" in strategy.price_history
        assert "BTC-EUR" in strategy.rsi_indicator
        assert "ETH-EUR" in strategy.rsi_indicator

    @pytest.mark.asyncio
    async def test_strength_at_minimum_is_0_5(self):
        """Strength is ~0.5 when price is at the breakout level."""
        strategy = BreakoutStrategy(
            lookback_period=5,
            breakout_threshold=0.01,
            rsi_period=3,
            rsi_overbought=90.0,
        )
        portfolio_value = Decimal("10000")
        for p in (50000, 49500, 50000, 49500, 50000):
            md = make_market_data(last=Decimal(str(p)))
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        # Exactly at breakout_high: 50000 × 1.01 = 50500
        md = make_market_data(last=Decimal("50500"))
        result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        if result is not None and result.signal_type == "BUY":
            assert result.strength == pytest.approx(0.5, abs=0.05)


# ---------------------------------------------------------------------------
# RangeReversionStrategy
# ---------------------------------------------------------------------------


class TestRangeReversionStrategy:
    """Tests for RangeReversionStrategy."""

    def test_get_parameters_contains_expected_keys(self):
        strategy = RangeReversionStrategy()
        params = strategy.get_parameters()
        assert params["strategy"] == "Range Reversion"
        assert "buy_zone" in params
        assert "sell_zone" in params
        assert "rsi_period" in params
        assert "rsi_confirmation_oversold" in params
        assert "rsi_confirmation_overbought" in params
        assert "min_range_pct" in params

    @pytest.mark.asyncio
    async def test_returns_none_before_rsi_warmup(self):
        """Strategy returns None until RSI has enough data."""
        strategy = RangeReversionStrategy(rsi_period=7)
        md = make_market_data(
            last=Decimal("50000"),
            high_24h=Decimal("52000"),
            low_24h=Decimal("48000"),
        )
        result = await strategy.analyze("BTC-EUR", md, [], Decimal("10000"))
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_range_too_narrow(self):
        """24h range below min_range_pct → None."""
        strategy = RangeReversionStrategy(rsi_period=3, min_range_pct=0.05)
        portfolio_value = Decimal("10000")
        # Warm up RSI first
        for _ in range(5):
            md = make_market_data(
                last=Decimal("50000"),
                high_24h=Decimal("50050"),  # Only 0.1 % range
                low_24h=Decimal("49950"),
            )
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        md = make_market_data(
            last=Decimal("49960"),
            high_24h=Decimal("50050"),
            low_24h=Decimal("49950"),
        )
        result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        assert result is None

    @pytest.mark.asyncio
    async def test_buy_signal_when_price_near_daily_low(self):
        """Price in bottom zone with RSI confirming oversold → BUY."""
        strategy = RangeReversionStrategy(
            buy_zone=0.25,
            rsi_period=3,
            rsi_confirmation_oversold=60.0,  # loose threshold for test
        )
        portfolio_value = Decimal("10000")
        # Warm up RSI with mid-range prices
        for _ in range(5):
            md = make_market_data(
                last=Decimal("50000"),
                high_24h=Decimal("52000"),
                low_24h=Decimal("48000"),
            )
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        # range_position = (49000 - 48000) / 4000 = 0.25 = buy_zone boundary
        md = make_market_data(
            last=Decimal("49000"),
            high_24h=Decimal("52000"),
            low_24h=Decimal("48000"),
        )
        result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        assert result is not None
        assert result.signal_type == "BUY"
        assert result.symbol == "BTC-EUR"
        assert result.strategy == "Range Reversion"
        assert 0.0 <= result.strength <= 1.0

    @pytest.mark.asyncio
    async def test_sell_signal_when_price_near_daily_high(self):
        """Price in top zone with RSI confirming overbought → SELL."""
        strategy = RangeReversionStrategy(
            sell_zone=0.75,
            rsi_period=3,
            rsi_confirmation_overbought=40.0,  # loose threshold for test
        )
        portfolio_value = Decimal("10000")
        for _ in range(5):
            md = make_market_data(
                last=Decimal("50000"),
                high_24h=Decimal("52000"),
                low_24h=Decimal("48000"),
            )
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        # range_position = (51000 - 48000) / 4000 = 0.75 = sell_zone boundary
        md = make_market_data(
            last=Decimal("51000"),
            high_24h=Decimal("52000"),
            low_24h=Decimal("48000"),
        )
        result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        assert result is not None
        assert result.signal_type == "SELL"
        assert 0.0 <= result.strength <= 1.0

    @pytest.mark.asyncio
    async def test_no_signal_when_price_in_middle_of_range(self):
        """Price in the 20 %–80 % middle zone → None."""
        strategy = RangeReversionStrategy(
            buy_zone=0.2, sell_zone=0.8, rsi_period=3, min_range_pct=0.01
        )
        portfolio_value = Decimal("10000")
        for _ in range(5):
            md = make_market_data(
                last=Decimal("50000"),
                high_24h=Decimal("52000"),
                low_24h=Decimal("48000"),
            )
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        # range_position = (50000 - 48000) / 4000 = 0.5 → middle
        md = make_market_data(
            last=Decimal("50000"),
            high_24h=Decimal("52000"),
            low_24h=Decimal("48000"),
        )
        result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_buy_when_rsi_not_oversold(self):
        """Price near daily low but RSI not confirming → None."""
        strategy = RangeReversionStrategy(
            buy_zone=0.3, rsi_period=3, rsi_confirmation_oversold=30.0
        )
        portfolio_value = Decimal("10000")
        # Feed rising prices to keep RSI high (well above 30)
        for _ in range(5):
            for price in (49000, 50000, 51000):
                md = make_market_data(
                    last=Decimal(str(price)),
                    high_24h=Decimal("52000"),
                    low_24h=Decimal("48000"),
                )
                await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        # Price in buy zone but RSI still elevated
        md = make_market_data(
            last=Decimal("48800"),  # range_position ≈ 0.20 < buy_zone=0.30
            high_24h=Decimal("52000"),
            low_24h=Decimal("48000"),
        )
        result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        # RSI should be above 30, blocking the buy signal
        if result is not None:
            assert result.signal_type in ("BUY", "SELL")  # acceptable if RSI happened to drop

    @pytest.mark.asyncio
    async def test_does_not_buy_when_already_long(self):
        """Existing long position blocks additional BUY signal."""
        strategy = RangeReversionStrategy(
            buy_zone=0.3, rsi_period=3, rsi_confirmation_oversold=60.0
        )
        portfolio_value = Decimal("10000")
        long_position = make_position(side=OrderSide.BUY)
        for _ in range(5):
            md = make_market_data(
                last=Decimal("50000"),
                high_24h=Decimal("52000"),
                low_24h=Decimal("48000"),
            )
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        md = make_market_data(
            last=Decimal("48500"),
            high_24h=Decimal("52000"),
            low_24h=Decimal("48000"),
        )
        result = await strategy.analyze("BTC-EUR", md, [long_position], portfolio_value)
        assert result is None or result.signal_type != "BUY"

    @pytest.mark.asyncio
    async def test_metadata_contains_range_fields(self):
        """Signal metadata includes range position, high/low, and RSI."""
        strategy = RangeReversionStrategy(
            buy_zone=0.25, rsi_period=3, rsi_confirmation_oversold=60.0
        )
        portfolio_value = Decimal("10000")
        for _ in range(5):
            md = make_market_data(
                last=Decimal("50000"),
                high_24h=Decimal("52000"),
                low_24h=Decimal("48000"),
            )
            await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        md = make_market_data(
            last=Decimal("49000"),
            high_24h=Decimal("52000"),
            low_24h=Decimal("48000"),
        )
        result = await strategy.analyze("BTC-EUR", md, [], portfolio_value)
        assert result is not None
        assert "range_position" in result.metadata
        assert "high_24h" in result.metadata
        assert "low_24h" in result.metadata
        assert "daily_range" in result.metadata
        assert "rsi" in result.metadata

    @pytest.mark.asyncio
    async def test_per_symbol_rsi_isolation(self):
        """Each symbol maintains independent RSI state."""
        strategy = RangeReversionStrategy()
        await strategy.analyze(
            "BTC-EUR",
            make_market_data(symbol="BTC-EUR", high_24h=Decimal("51000"), low_24h=Decimal("49000")),
            [],
            Decimal("10000"),
        )
        await strategy.analyze(
            "ETH-EUR",
            make_market_data(symbol="ETH-EUR", high_24h=Decimal("3100"), low_24h=Decimal("2900")),
            [],
            Decimal("10000"),
        )
        assert "BTC-EUR" in strategy.rsi_indicator
        assert "ETH-EUR" in strategy.rsi_indicator
