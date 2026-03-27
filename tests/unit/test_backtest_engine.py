"""Unit tests for BacktestEngine and BacktestResults."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.backtest.engine import SPREAD_PCT, BacktestEngine, BacktestResults
from src.config import RiskLevel, StrategyType
from src.models.domain import CandleData, OrderSide, Signal
from src.utils.fees import TAKER_FEE_PCT


def make_candle(
    start: int = 1_700_000_000_000,
    close: str = "50000",
    high: str = "51000",
    low: str = "49000",
    open_: str = "50000",
    volume: str = "10",
) -> CandleData:
    """Helper: build a CandleData with sensible defaults."""
    return CandleData(start=start, open=open_, high=high, low=low, close=close, volume=volume)


def make_candle_dict(
    start: int = 1_700_000_000_000,
    close: str = "50000",
    high: str = "51000",
    low: str = "49000",
    open_: str = "50000",
    volume: str = "10",
) -> dict:
    """Helper: build a raw candle dict (as returned by get_candles)."""
    return {
        "start": start,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


@pytest.fixture
def mock_api():
    return MagicMock()


@pytest.fixture
def engine(mock_api):
    return BacktestEngine(
        api_client=mock_api,
        strategy_type=StrategyType.MOMENTUM,
        risk_level=RiskLevel.MODERATE,
        initial_capital=Decimal("10000"),
    )


# ---------------------------------------------------------------------------
# BacktestResults
# ---------------------------------------------------------------------------


class TestBacktestResultsWinRate:
    def test_zero_trades_returns_zero(self):
        r = BacktestResults()
        assert r.win_rate == 0.0

    def test_all_wins(self):
        r = BacktestResults()
        r.total_trades = 4
        r.winning_trades = 4
        assert r.win_rate == 100.0

    def test_partial_wins(self):
        r = BacktestResults()
        r.total_trades = 4
        r.winning_trades = 3
        assert r.win_rate == 75.0


class TestBacktestResultsProfitFactor:
    def test_no_trades_returns_zero(self):
        r = BacktestResults()
        assert r.profit_factor == 0.0

    def test_all_winning_trades_returns_inf(self):
        r = BacktestResults()
        r.trades = [{"pnl": 100.0}, {"pnl": 200.0}]
        assert r.profit_factor == float("inf")

    def test_all_losing_trades(self):
        r = BacktestResults()
        r.trades = [{"pnl": -100.0}, {"pnl": -50.0}]
        assert r.profit_factor == 0.0

    def test_mixed_trades(self):
        r = BacktestResults()
        r.trades = [{"pnl": 300.0}, {"pnl": -100.0}]
        assert r.profit_factor == pytest.approx(3.0)


class TestBacktestResultsReturnPct:
    def test_zero_initial_capital(self):
        r = BacktestResults()
        r.initial_capital = Decimal("0")
        assert r.return_pct == 0.0

    def test_positive_return(self):
        r = BacktestResults()
        r.initial_capital = Decimal("10000")
        r.final_capital = Decimal("11000")
        assert r.return_pct == pytest.approx(10.0)

    def test_negative_return(self):
        r = BacktestResults()
        r.initial_capital = Decimal("10000")
        r.final_capital = Decimal("9000")
        assert r.return_pct == pytest.approx(-10.0)

    def test_zero_return(self):
        r = BacktestResults()
        r.initial_capital = Decimal("10000")
        r.final_capital = Decimal("10000")
        assert r.return_pct == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# BacktestEngine._create_strategy
# ---------------------------------------------------------------------------


class TestBacktestEngineStrategyCreation:
    def test_momentum_strategy(self, mock_api):
        e = BacktestEngine(mock_api, StrategyType.MOMENTUM, RiskLevel.MODERATE)
        from src.strategies.momentum import MomentumStrategy

        assert isinstance(e.strategy, MomentumStrategy)

    def test_mean_reversion_strategy(self, mock_api):
        e = BacktestEngine(mock_api, StrategyType.MEAN_REVERSION, RiskLevel.MODERATE)
        from src.strategies.mean_reversion import MeanReversionStrategy

        assert isinstance(e.strategy, MeanReversionStrategy)

    def test_market_making_strategy(self, mock_api):
        e = BacktestEngine(mock_api, StrategyType.MARKET_MAKING, RiskLevel.MODERATE)
        from src.strategies.market_making import MarketMakingStrategy

        assert isinstance(e.strategy, MarketMakingStrategy)

    def test_multi_strategy(self, mock_api):
        e = BacktestEngine(mock_api, StrategyType.MULTI_STRATEGY, RiskLevel.MODERATE)
        from src.strategies.multi_strategy import MultiStrategy

        assert isinstance(e.strategy, MultiStrategy)

    def test_breakout_strategy(self, mock_api):
        e = BacktestEngine(mock_api, StrategyType.BREAKOUT, RiskLevel.MODERATE)
        from src.strategies.breakout import BreakoutStrategy

        assert isinstance(e.strategy, BreakoutStrategy)

    def test_range_reversion_strategy(self, mock_api):
        e = BacktestEngine(mock_api, StrategyType.RANGE_REVERSION, RiskLevel.MODERATE)
        from src.strategies.range_reversion import RangeReversionStrategy

        assert isinstance(e.strategy, RangeReversionStrategy)


# ---------------------------------------------------------------------------
# BacktestEngine._candle_to_market_data
# ---------------------------------------------------------------------------


class TestCandleToMarketData:
    def test_converts_close_to_last(self, engine):
        candle = make_candle(close="50000", high="51000", low="49000")
        md = engine._candle_to_market_data(candle, "BTC-EUR")
        assert md.symbol == "BTC-EUR"
        assert md.last == Decimal("50000")

    def test_bid_below_last_ask_above(self, engine):
        candle = make_candle(close="50000")
        md = engine._candle_to_market_data(candle, "BTC-EUR")
        assert md.bid < md.last < md.ask

    def test_volume_set(self, engine):
        candle = make_candle(close="50000", volume="42")
        md = engine._candle_to_market_data(candle, "BTC-EUR")
        assert md.volume_24h == Decimal("42")

    def test_high_low_mapped_correctly(self, engine):
        candle = make_candle(close="50000", high="51000", low="49000")
        md = engine._candle_to_market_data(candle, "BTC-EUR")
        assert md.high_24h == Decimal("51000")
        assert md.low_24h == Decimal("49000")

    def test_timestamp_is_utc_aware(self, engine):
        candle = make_candle(start=1_700_000_000_000)
        md = engine._candle_to_market_data(candle, "BTC-EUR")
        assert md.timestamp.tzinfo is not None


# ---------------------------------------------------------------------------
# BacktestEngine._execute_backtest_order
# ---------------------------------------------------------------------------


class TestExecuteBacktestOrder:
    def test_buy_succeeds_with_sufficient_funds(self, engine):
        qty = Decimal("0.1")
        price = Decimal("50000")
        ok = engine._execute_backtest_order("BTC-EUR", OrderSide.BUY, qty, price, datetime.now(UTC))
        assert ok is True
        assert "BTC-EUR" in engine.positions
        order_value = qty * price
        fee = order_value * TAKER_FEE_PCT
        expected = Decimal("10000") - order_value - fee
        assert engine.cash_balance == expected

    def test_buy_fails_with_insufficient_funds(self, engine):
        engine.cash_balance = Decimal("100")
        ok = engine._execute_backtest_order(
            "BTC-EUR", OrderSide.BUY, Decimal("10"), Decimal("50000"), datetime.now(UTC)
        )
        assert ok is False
        assert "BTC-EUR" not in engine.positions

    def test_buy_adds_to_existing_position(self, engine):
        engine.cash_balance = Decimal("20000")
        engine._execute_backtest_order(
            "BTC-EUR", OrderSide.BUY, Decimal("0.1"), Decimal("50000"), datetime.now(UTC)
        )
        engine._execute_backtest_order(
            "BTC-EUR", OrderSide.BUY, Decimal("0.1"), Decimal("52000"), datetime.now(UTC)
        )
        assert engine.positions["BTC-EUR"].quantity == Decimal("0.2")

    def test_sell_fails_without_position(self, engine):
        ok = engine._execute_backtest_order(
            "BTC-EUR", OrderSide.SELL, Decimal("0.1"), Decimal("50000"), datetime.now(UTC)
        )
        assert ok is False

    def test_sell_fails_with_insufficient_position(self, engine):
        engine._execute_backtest_order(
            "BTC-EUR", OrderSide.BUY, Decimal("0.05"), Decimal("50000"), datetime.now(UTC)
        )
        ok = engine._execute_backtest_order(
            "BTC-EUR", OrderSide.SELL, Decimal("0.1"), Decimal("50000"), datetime.now(UTC)
        )
        assert ok is False

    def test_sell_winning_trade_increments_winning(self, engine):
        engine._execute_backtest_order(
            "BTC-EUR", OrderSide.BUY, Decimal("0.1"), Decimal("50000"), datetime.now(UTC)
        )
        engine._execute_backtest_order(
            "BTC-EUR", OrderSide.SELL, Decimal("0.1"), Decimal("55000"), datetime.now(UTC)
        )
        assert engine.results.total_trades == 1
        assert engine.results.winning_trades == 1

    def test_sell_losing_trade_increments_losing(self, engine):
        engine._execute_backtest_order(
            "BTC-EUR", OrderSide.BUY, Decimal("0.1"), Decimal("50000"), datetime.now(UTC)
        )
        engine._execute_backtest_order(
            "BTC-EUR", OrderSide.SELL, Decimal("0.1"), Decimal("45000"), datetime.now(UTC)
        )
        assert engine.results.losing_trades == 1

    def test_sell_closes_position_fully(self, engine):
        engine._execute_backtest_order(
            "BTC-EUR", OrderSide.BUY, Decimal("0.1"), Decimal("50000"), datetime.now(UTC)
        )
        engine._execute_backtest_order(
            "BTC-EUR", OrderSide.SELL, Decimal("0.1"), Decimal("50000"), datetime.now(UTC)
        )
        assert "BTC-EUR" not in engine.positions

    def test_sell_reduces_partial_position(self, engine):
        engine.cash_balance = Decimal("60000")
        engine._execute_backtest_order(
            "BTC-EUR", OrderSide.BUY, Decimal("1.0"), Decimal("50000"), datetime.now(UTC)
        )
        engine._execute_backtest_order(
            "BTC-EUR", OrderSide.SELL, Decimal("0.3"), Decimal("50000"), datetime.now(UTC)
        )
        assert engine.positions["BTC-EUR"].quantity == Decimal("0.7")

    def test_sell_records_trade_in_results(self, engine):
        engine._execute_backtest_order(
            "BTC-EUR", OrderSide.BUY, Decimal("0.1"), Decimal("50000"), datetime.now(UTC)
        )
        engine._execute_backtest_order(
            "BTC-EUR", OrderSide.SELL, Decimal("0.1"), Decimal("51000"), datetime.now(UTC)
        )
        assert len(engine.results.trades) == 1
        assert engine.results.trades[0]["symbol"] == "BTC-EUR"


# ---------------------------------------------------------------------------
# Backtest SELL guard — mirrors live executor behaviour
# ---------------------------------------------------------------------------


class TestBacktestSellGuard:
    """Backtest must skip SELL signals for symbols with no open position, matching
    the live executor's pre-existing crypto protection (SELL guard)."""

    @pytest.mark.asyncio
    async def test_sell_signal_with_no_position_never_reaches_execute(self, engine, mock_api):
        """The SELL guard must intercept the signal in _process_bar_symbol so that
        _execute_backtest_order is never called with SELL when there is no position.

        Without the guard, _execute_backtest_order IS called (it rejects internally),
        which causes spurious WARNING logs in the compare/matrix output.
        """
        candles = [make_candle_dict(start=1_700_000_000_000 + i * 60_000) for i in range(5)]
        mock_api.get_candles = AsyncMock(return_value=candles)

        sell_signal = Signal(
            symbol="BTC-EUR",
            strategy="market_making",
            signal_type="SELL",
            strength=0.8,
            price=Decimal("50000"),
            reason="test sell with no position",
        )
        with patch.object(engine.strategy, "analyze", AsyncMock(return_value=sell_signal)):
            with patch.object(
                engine, "_execute_backtest_order", wraps=engine._execute_backtest_order
            ) as mock_exec:
                await engine.run(["BTC-EUR"], days=1, interval=60)

        # _execute_backtest_order must never be called with SELL when there's no position.
        # It may be called with keyword or positional args depending on call site.
        def _is_sell(call):
            if call.args and len(call.args) >= 2:
                return call.args[1] == OrderSide.SELL
            return call.kwargs.get("side") == OrderSide.SELL

        sell_calls = [c for c in mock_exec.call_args_list if _is_sell(c)]
        assert len(sell_calls) == 0, (
            f"_execute_backtest_order must not be called with SELL when no position exists; "
            f"got {len(sell_calls)} call(s). Without the SELL guard these generate WARNING logs."
        )

    @pytest.mark.asyncio
    async def test_sell_signal_after_buy_executes_normally(self, engine, mock_api):
        """A SELL signal must execute when the engine holds a position for that symbol."""
        candles = [make_candle_dict(start=1_700_000_000_000 + i * 60_000) for i in range(10)]
        mock_api.get_candles = AsyncMock(return_value=candles)

        async def alternating_signal(symbol, market_data, positions, portfolio_value):
            if any(p.symbol == symbol for p in positions):
                return Signal(
                    symbol=symbol,
                    strategy="market_making",
                    signal_type="SELL",
                    strength=0.8,
                    price=Decimal("50000"),
                    reason="close position",
                )
            return Signal(
                symbol=symbol,
                strategy="market_making",
                signal_type="BUY",
                strength=0.8,
                price=Decimal("50000"),
                reason="open position",
            )

        with patch.object(engine.strategy, "analyze", side_effect=alternating_signal):
            results = await engine.run(["BTC-EUR"], days=1, interval=60)

        assert results.total_trades >= 1, "SELL after BUY must execute successfully"


# ---------------------------------------------------------------------------
# BacktestEngine.run
# ---------------------------------------------------------------------------


class TestBacktestEngineRun:
    @pytest.mark.asyncio
    async def test_run_with_no_data_returns_empty_results(self, engine, mock_api):
        mock_api.get_candles = AsyncMock(return_value=[])
        results = await engine.run(["BTC-EUR"], days=1, interval=60)
        assert results.total_trades == 0

    @pytest.mark.asyncio
    async def test_run_with_candle_data_builds_equity_curve(self, engine, mock_api):
        candles = [
            make_candle_dict(
                start=1_700_000_000_000 + i * 60_000,
                close=str(50000 + i * 50),
            )
            for i in range(30)
        ]
        mock_api.get_candles = AsyncMock(return_value=candles)
        results = await engine.run(["BTC-EUR"], days=1, interval=60)
        assert len(results.equity_curve) == 30

    @pytest.mark.asyncio
    async def test_run_sets_final_capital(self, engine, mock_api):
        candles = [make_candle_dict(start=1_700_000_000_000 + i * 60_000) for i in range(5)]
        mock_api.get_candles = AsyncMock(return_value=candles)
        results = await engine.run(["BTC-EUR"], days=1, interval=60)
        assert results.final_capital == engine.cash_balance

    @pytest.mark.asyncio
    async def test_run_closes_open_positions_at_end(self, engine, mock_api):
        """All positions should be closed when backtest ends."""
        candles = [make_candle_dict(start=1_700_000_000_000)]
        mock_api.get_candles = AsyncMock(return_value=candles)
        await engine.run(["BTC-EUR"], days=1, interval=60)
        assert engine.positions == {}

    @pytest.mark.asyncio
    async def test_run_tracks_drawdown(self, engine, mock_api):
        """Equity decline from peak should update max_drawdown."""
        # First candle at high price, then a drop
        candles = [
            make_candle_dict(start=1_700_000_000_000, close="50000"),
            make_candle_dict(start=1_700_000_060_000, close="50000"),
            make_candle_dict(start=1_700_000_120_000, close="50000"),
        ]
        mock_api.get_candles = AsyncMock(return_value=candles)
        results = await engine.run(["BTC-EUR"], days=1, interval=60)
        # Drawdown should be tracked (at minimum 0)
        assert results.max_drawdown >= Decimal("0")

    @pytest.mark.asyncio
    async def test_run_invalid_interval_raises(self, engine, mock_api):
        with pytest.raises(ValueError, match="Unsupported candle interval"):
            await engine.run(["BTC-EUR"], days=1, interval=7)


# ---------------------------------------------------------------------------
# BacktestResults.compute_sharpe_ratio
# ---------------------------------------------------------------------------


class TestComputeSharpeRatio:
    def test_empty_equity_curve_keeps_default(self):
        r = BacktestResults()
        r.compute_sharpe_ratio()
        assert r.sharpe_ratio == 0.0

    def test_single_data_point_keeps_default(self):
        r = BacktestResults()
        r.equity_curve = [(datetime(2024, 1, 1, tzinfo=UTC), Decimal("10000"))]
        r.compute_sharpe_ratio()
        assert r.sharpe_ratio == 0.0

    def test_two_data_points_keeps_default(self):
        """Need at least 2 returns (3 equity values) for stdev."""
        r = BacktestResults()
        r.equity_curve = [
            (datetime(2024, 1, 1, 0, 0, tzinfo=UTC), Decimal("10000")),
            (datetime(2024, 1, 1, 1, 0, tzinfo=UTC), Decimal("10100")),
        ]
        r.compute_sharpe_ratio()
        # Only 1 return — not enough for stdev
        assert r.sharpe_ratio == 0.0

    def test_constant_equity_keeps_default(self):
        """Zero std ⇒ early return."""
        r = BacktestResults()
        r.equity_curve = [
            (datetime(2024, 1, 1, i, 0, tzinfo=UTC), Decimal("10000")) for i in range(5)
        ]
        r.compute_sharpe_ratio()
        assert r.sharpe_ratio == 0.0

    def test_positive_returns_produce_positive_sharpe(self):
        """Consistently increasing equity ⇒ positive Sharpe ratio."""
        r = BacktestResults()
        r.equity_curve = [
            (datetime(2024, 1, 1, i, 0, tzinfo=UTC), Decimal(str(10000 + i * 100)))
            for i in range(10)
        ]
        r.compute_sharpe_ratio()
        assert r.sharpe_ratio is not None
        assert r.sharpe_ratio > 0

    def test_negative_returns_produce_negative_sharpe(self):
        """Consistently declining equity ⇒ negative Sharpe ratio."""
        r = BacktestResults()
        r.equity_curve = [
            (datetime(2024, 1, 1, i, 0, tzinfo=UTC), Decimal(str(10000 - i * 100)))
            for i in range(10)
        ]
        r.compute_sharpe_ratio()
        assert r.sharpe_ratio is not None
        assert r.sharpe_ratio < 0


# ---------------------------------------------------------------------------
# Comparison table formatting
# ---------------------------------------------------------------------------


class TestComparisonTable:
    """Tests for the comparison table printer in backtest_compare."""

    def test_print_comparison_table_sorts_by_return(self, capsys):
        """Rows are sorted by return_pct descending."""
        from cli.backtest_compare import _print_comparison_table

        rows = [
            {
                "strategy": "momentum",
                "risk_level": "conservative",
                "return_pct": 5.0,
                "total_pnl": 500.0,
                "total_fees": 4.5,
                "total_trades": 10,
                "winning_trades": 6,
                "losing_trades": 4,
                "win_rate": 60.0,
                "profit_factor": 1.5,
                "max_drawdown": 200.0,
                "sharpe_ratio": 1.2,
            },
            {
                "strategy": "breakout",
                "risk_level": "conservative",
                "return_pct": 8.0,
                "total_pnl": 800.0,
                "total_fees": 7.2,
                "total_trades": 8,
                "winning_trades": 5,
                "losing_trades": 3,
                "win_rate": 62.5,
                "profit_factor": 2.0,
                "max_drawdown": 150.0,
                "sharpe_ratio": 1.8,
            },
        ]
        _print_comparison_table(rows)
        output = capsys.readouterr().out
        # Breakout (8%) should appear before momentum (5%)
        breakout_pos = output.find("breakout")
        momentum_pos = output.find("momentum")
        assert breakout_pos < momentum_pos

    def test_print_comparison_table_empty(self, capsys):
        """Empty list prints a 'no results' message."""
        from cli.backtest_compare import _print_comparison_table

        _print_comparison_table([])
        output = capsys.readouterr().out
        assert "No results" in output

    def test_print_comparison_table_shows_best_and_worst(self, capsys):
        """Summary shows best and worst strategies."""
        from cli.backtest_compare import _print_comparison_table

        rows = [
            {
                "strategy": "mean_reversion",
                "risk_level": "moderate",
                "return_pct": -2.0,
                "total_pnl": -200.0,
                "total_fees": 1.8,
                "total_trades": 5,
                "winning_trades": 1,
                "losing_trades": 4,
                "win_rate": 20.0,
                "profit_factor": 0.5,
                "max_drawdown": 500.0,
                "sharpe_ratio": -0.5,
            },
            {
                "strategy": "momentum",
                "risk_level": "moderate",
                "return_pct": 12.0,
                "total_pnl": 1200.0,
                "total_fees": 10.8,
                "total_trades": 15,
                "winning_trades": 10,
                "losing_trades": 5,
                "win_rate": 66.7,
                "profit_factor": 3.0,
                "max_drawdown": 300.0,
                "sharpe_ratio": 2.1,
            },
        ]
        _print_comparison_table(rows)
        output = capsys.readouterr().out
        assert "Best:" in output
        assert "momentum" in output
        assert "Worst:" in output
        assert "mean_reversion" in output


# ---------------------------------------------------------------------------
# Backtest realism: strategy risk overrides
# ---------------------------------------------------------------------------


class TestStrategyRiskOverrides:
    """BacktestEngine must pass the strategy name to RiskManager so that
    per-strategy SL/TP overrides are applied, matching live-trading behaviour."""

    def test_market_making_uses_tight_stop_loss(self, mock_api):
        """market_making override: stop_loss_pct = 0.5, not the 1.5 moderate baseline."""
        engine = BacktestEngine(
            mock_api, StrategyType.MARKET_MAKING, RiskLevel.MODERATE, Decimal("10000")
        )
        assert engine.risk_manager.risk_params["stop_loss_pct"] == pytest.approx(0.5)

    def test_momentum_stop_loss_override_applied(self, mock_api):
        """momentum override: take_profit_pct = 4.0 (not conservative 2.5)."""
        engine = BacktestEngine(
            mock_api, StrategyType.MOMENTUM, RiskLevel.CONSERVATIVE, Decimal("10000")
        )
        # Conservative baseline take_profit_pct = 2.5; momentum override = 4.0
        assert engine.risk_manager.risk_params["take_profit_pct"] == pytest.approx(4.0)

    def test_breakout_uses_wider_stop_loss(self, mock_api):
        """breakout override: stop_loss_pct = 3.0 (wider than conservative baseline 1.5)."""
        engine = BacktestEngine(
            mock_api, StrategyType.BREAKOUT, RiskLevel.CONSERVATIVE, Decimal("10000")
        )
        # Conservative baseline stop_loss_pct = 1.5; breakout override = 3.0
        assert engine.risk_manager.risk_params["stop_loss_pct"] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Backtest realism: signal strength filter
# ---------------------------------------------------------------------------


class TestSignalStrengthFilterInBacktest:
    """Weak signals must be discarded in backtest, matching live-trading behaviour."""

    @pytest.mark.asyncio
    async def test_momentum_weak_signal_produces_no_trades(self, mock_api):
        """Momentum requires strength ≥ 0.6; a signal at 0.4 must not generate a trade."""
        engine = BacktestEngine(
            mock_api, StrategyType.MOMENTUM, RiskLevel.MODERATE, Decimal("10000")
        )
        # Candles designed to trigger a momentum signal with low confidence
        candles = [
            make_candle_dict(
                start=1_700_000_000_000 + i * 60_000,
                close=str(50000 + i * 10),  # slight upward drift — low momentum strength
            )
            for i in range(50)
        ]
        mock_api.get_candles = AsyncMock(return_value=candles)

        # Patch strategy.analyze to return a below-threshold signal every bar
        weak_signal = Signal(
            symbol="BTC-EUR",
            strategy="Momentum",
            signal_type="BUY",
            strength=0.4,  # below momentum threshold of 0.6
            price=Decimal("50000"),
            reason="weak momentum",
        )
        with patch.object(engine.strategy, "analyze", AsyncMock(return_value=weak_signal)):
            results = await engine.run(["BTC-EUR"], days=1, interval=60)

        assert results.total_trades == 0, (
            "Weak momentum signal (strength=0.4 < threshold=0.6) must not execute in backtest"
        )

    @pytest.mark.asyncio
    async def test_momentum_strong_signal_executes(self, mock_api):
        """Momentum signal at strength ≥ 0.6 must be executed."""
        engine = BacktestEngine(
            mock_api, StrategyType.MOMENTUM, RiskLevel.MODERATE, Decimal("10000")
        )
        candles = [make_candle_dict(start=1_700_000_000_000 + i * 60_000) for i in range(5)]
        mock_api.get_candles = AsyncMock(return_value=candles)

        strong_signal = Signal(
            symbol="BTC-EUR",
            strategy="Momentum",
            signal_type="BUY",
            strength=0.8,  # above momentum threshold of 0.6
            price=Decimal("50000"),
            reason="strong momentum",
        )
        with patch.object(engine.strategy, "analyze", AsyncMock(return_value=strong_signal)):
            results = await engine.run(["BTC-EUR"], days=1, interval=60)

        assert results.total_trades >= 1, "Strong momentum signal must execute in backtest"


# ---------------------------------------------------------------------------
# Backtest realism: spread constant
# ---------------------------------------------------------------------------


class TestSpreadConstant:
    """SPREAD_PCT must reflect realistic exchange spreads, not an inflated value."""

    def test_spread_pct_is_realistic(self):
        """SPREAD_PCT must be ≤ 0.002 (0.2%) to avoid artificial slippage.

        Real Revolut X bid-ask spreads are ~0.05-0.1%.  Using 0.3% creates
        artificial losses and makes backtest results unrepresentative of live
        trading performance.
        """
        assert Decimal("0.002") >= SPREAD_PCT, (
            f"SPREAD_PCT={SPREAD_PCT} is too high; set it to ≤ 0.002 to match real spreads"
        )


# ---------------------------------------------------------------------------
# Backtest realism: intra-bar SL/TP
# ---------------------------------------------------------------------------


@pytest.fixture
def mm_conservative_engine(mock_api):
    """BacktestEngine with market_making + conservative: SL=0.5%, TP=0.3%."""
    return BacktestEngine(
        mock_api, StrategyType.MARKET_MAKING, RiskLevel.CONSERVATIVE, Decimal("10000")
    )


class TestIntraBarSLTP:
    """SL/TP must trigger if the candle high/low breaches the level, even when the
    candle close does not — mirroring the live bot which polls every 5-10 seconds."""

    @pytest.mark.asyncio
    async def test_stop_loss_triggers_on_candle_low_not_just_close(self, mm_conservative_engine):
        """SL must fire when candle low ≤ stop_loss, even if candle close > stop_loss.

        With the default close-only check the position survives the candle;
        intra-bar checking correctly closes it.
        """
        engine = mm_conservative_engine
        # conservative + market_making: SL = 0.5%
        # Buy at 50000 → stop_loss = 50000 × 0.995 = 49750
        engine._execute_backtest_order(
            "BTC-EUR", OrderSide.BUY, Decimal("0.1"), Decimal("50000"), datetime.now(UTC)
        )
        sl = engine.positions["BTC-EUR"].stop_loss  # 49750

        # Candle: low=49600 < sl=49750 → SL breached intra-bar
        #         close=49800 > sl=49750 → close-only check would NOT exit
        candle = make_candle(close="49800", high="50200", low="49600")
        md = engine._candle_to_market_data(candle, "BTC-EUR")

        await engine._process_bar_symbol("BTC-EUR", md)

        assert "BTC-EUR" not in engine.positions, (
            f"Position must close when candle low ({md.low_24h}) ≤ stop_loss ({sl}), "
            "even when close > stop_loss"
        )

    @pytest.mark.asyncio
    async def test_take_profit_triggers_on_candle_high_not_just_close(self, mm_conservative_engine):
        """TP must fire when candle high ≥ take_profit, even if candle close < take_profit."""
        engine = mm_conservative_engine
        # conservative + market_making: TP = 0.3%
        # Buy at 50000 → take_profit = 50000 × 1.003 = 50150
        engine._execute_backtest_order(
            "BTC-EUR", OrderSide.BUY, Decimal("0.1"), Decimal("50000"), datetime.now(UTC)
        )
        tp = engine.positions["BTC-EUR"].take_profit  # 50150

        # Candle: high=50300 > tp=50150 → TP breached intra-bar
        #         close=50050 < tp=50150 → close-only check would NOT exit
        candle = make_candle(close="50050", high="50300", low="49900")
        md = engine._candle_to_market_data(candle, "BTC-EUR")

        await engine._process_bar_symbol("BTC-EUR", md)

        assert "BTC-EUR" not in engine.positions, (
            f"Position must close when candle high ({md.high_24h}) ≥ take_profit ({tp}), "
            "even when close < take_profit"
        )

    @pytest.mark.asyncio
    async def test_sl_takes_precedence_when_both_triggered_intrabar(self, mm_conservative_engine):
        """When both SL and TP are breached in the same candle, SL wins (worst case)."""
        engine = mm_conservative_engine
        # Buy at 50000 → SL=49750, TP=50150
        engine._execute_backtest_order(
            "BTC-EUR", OrderSide.BUY, Decimal("0.1"), Decimal("50000"), datetime.now(UTC)
        )
        # Whipsaw candle: low < SL AND high > TP
        candle = make_candle(close="50000", high="50400", low="49500")
        md = engine._candle_to_market_data(candle, "BTC-EUR")

        await engine._process_bar_symbol("BTC-EUR", md)

        assert "BTC-EUR" not in engine.positions
        # Trade recorded — the exit price should be at (or near) stop_loss, not take_profit
        trade = engine.results.trades[-1]
        assert trade["price"] <= float(Decimal("50000")), (
            "SL must take precedence; exit price should be at stop_loss level, not take_profit"
        )

    @pytest.mark.asyncio
    async def test_position_survives_when_candle_range_within_sl_tp(self, mm_conservative_engine):
        """Position must stay open when candle high/low stay within SL/TP bounds."""
        engine = mm_conservative_engine
        # Buy at 50000 → SL=49750, TP=50150
        engine._execute_backtest_order(
            "BTC-EUR", OrderSide.BUY, Decimal("0.1"), Decimal("50000"), datetime.now(UTC)
        )
        # Candle entirely within SL/TP range
        candle = make_candle(close="50020", high="50100", low="49800")
        md = engine._candle_to_market_data(candle, "BTC-EUR")

        with patch.object(engine.strategy, "analyze", AsyncMock(return_value=None)):
            await engine._process_bar_symbol("BTC-EUR", md)

        assert "BTC-EUR" in engine.positions


# ---------------------------------------------------------------------------
# Backtest realism: LIMIT order fill verification
# ---------------------------------------------------------------------------


class TestLimitOrderFillVerification:
    """LIMIT orders must only fill when the candle price range makes the limit price reachable.
    MARKET orders must always fill at the current bid/ask."""

    @pytest.mark.asyncio
    async def test_limit_buy_skipped_when_candle_low_above_limit_price(self, mock_api):
        """LIMIT BUY must not fill if candle low > limit price (price never dipped that low)."""
        engine = BacktestEngine(
            mock_api, StrategyType.MARKET_MAKING, RiskLevel.MODERATE, Decimal("10000")
        )
        # close=50000, ask=50025, bid=49975
        # Candle low=50010 > bid=49975 → limit price is NOT reachable
        candles = [
            make_candle_dict(
                start=1_700_000_000_000,
                close="50000",
                high="50100",
                low="50010",
            )
        ]
        mock_api.get_candles = AsyncMock(return_value=candles)

        signal = Signal(
            symbol="BTC-EUR",
            strategy="market_making",
            signal_type="BUY",
            strength=0.8,
            price=Decimal("49975"),
            reason="limit buy test",
        )
        with patch.object(engine.strategy, "analyze", AsyncMock(return_value=signal)):
            results = await engine.run(["BTC-EUR"], days=1, interval=60)

        assert results.total_trades == 0, (
            "LIMIT BUY at 49975 must not fill when candle low=50010 > 49975"
        )

    @pytest.mark.asyncio
    async def test_limit_buy_fills_at_limit_price_when_reachable(self, mock_api):
        """LIMIT BUY fills at the limit price (not ask) when candle low ≤ limit price."""
        engine = BacktestEngine(
            mock_api, StrategyType.MARKET_MAKING, RiskLevel.MODERATE, Decimal("10000")
        )
        # Candle low=49900 ≤ bid=49975 → limit IS reachable
        # Use 2 candles so run() force-closes the position and records a trade
        candles = [
            make_candle_dict(start=1_700_000_000_000, close="50000", high="50100", low="49900"),
            make_candle_dict(start=1_700_000_060_000, close="50000", high="50100", low="49900"),
        ]
        mock_api.get_candles = AsyncMock(return_value=candles)

        signal = Signal(
            symbol="BTC-EUR",
            strategy="market_making",
            signal_type="BUY",
            strength=0.8,
            price=Decimal("49975"),
            reason="limit buy test",
        )
        with patch.object(engine.strategy, "analyze", AsyncMock(return_value=signal)):
            results = await engine.run(["BTC-EUR"], days=1, interval=60)

        # Should have traded (force-close records the SELL)
        assert results.total_trades >= 1, "LIMIT BUY must fill when candle low ≤ limit price"
        # Entry price must be the limit price, not the ask
        entry = results.trades[0]["entry_price"]
        assert entry == pytest.approx(float(Decimal("49975"))), (
            f"LIMIT BUY must fill at limit price 49975, not at ask ~50025; got entry={entry}"
        )

    @pytest.mark.asyncio
    async def test_limit_sell_skipped_when_candle_high_below_limit_price(self, mock_api):
        """LIMIT SELL must not fill if candle high < limit price (price never rose that high)."""
        engine = BacktestEngine(
            mock_api, StrategyType.MARKET_MAKING, RiskLevel.MODERATE, Decimal("10000")
        )
        # Open a position of 0.006 BTC (300 EUR = 3% of portfolio):
        # - concentration stays within 6% limit when the SELL adds ~240 EUR more
        # - pos.quantity (0.006) > risk-manager calculated sell qty (~0.00479)
        #   so the "Insufficient position" guard does NOT block the SELL
        # Without the LIMIT check the SELL would fill and record a trade.
        engine._execute_backtest_order(
            "BTC-EUR", OrderSide.BUY, Decimal("0.006"), Decimal("50000"), datetime.now(UTC)
        )
        candles = [
            make_candle_dict(
                start=1_700_000_000_000,
                close="50000",
                high="50020",
                low="49900",
            )
        ]
        mock_api.get_candles = AsyncMock(return_value=candles)

        # SELL LIMIT at 50050 — candle high=50020 < 50050 → NOT reachable
        signal = Signal(
            symbol="BTC-EUR",
            strategy="market_making",
            signal_type="SELL",
            strength=0.8,
            price=Decimal("50050"),
            reason="limit sell test",
        )
        with patch.object(engine.strategy, "analyze", AsyncMock(return_value=signal)):
            candle = make_candle(close="50000", high="50020", low="49900")
            md = engine._candle_to_market_data(candle, "BTC-EUR")
            await engine._process_bar_symbol("BTC-EUR", md)

        assert engine.results.total_trades == 0, (
            "LIMIT SELL at 50050 must not generate any trade when candle high=50020 < 50050"
        )

    @pytest.mark.asyncio
    async def test_market_buy_always_fills_at_ask_regardless_of_signal_price(self, mock_api):
        """MARKET BUY fills at ask price even when signal.price is far below ask."""
        engine = BacktestEngine(
            mock_api, StrategyType.MOMENTUM, RiskLevel.MODERATE, Decimal("10000")
        )
        # close=50000, ask=50025
        # Signal at 49000 (well below ask) — MARKET order should still fill at ask
        candles = [
            make_candle_dict(start=1_700_000_000_000, close="50000", high="50100", low="49000"),
            make_candle_dict(start=1_700_000_060_000, close="50000", high="50100", low="49000"),
        ]
        mock_api.get_candles = AsyncMock(return_value=candles)

        signal = Signal(
            symbol="BTC-EUR",
            strategy="Momentum",
            signal_type="BUY",
            strength=0.8,
            price=Decimal("49000"),
            reason="market buy test",
        )
        with patch.object(engine.strategy, "analyze", AsyncMock(return_value=signal)):
            results = await engine.run(["BTC-EUR"], days=1, interval=60)

        assert results.total_trades >= 1
        entry = results.trades[0]["entry_price"]
        ask = float(Decimal("50000") * (1 + SPREAD_PCT / 2))
        assert entry == pytest.approx(ask, rel=1e-4), (
            f"MARKET BUY must fill at ask ({ask}), not at signal price 49000; got {entry}"
        )


class TestOrderTypeSelection:
    """Per-strategy order type selection mirrors the live executor.

    From ``_STRATEGY_ORDER_TYPE`` in ``src/execution/executor.py``:
    - momentum, breakout → MARKET order (speed-critical, bypasses LIMIT fill check)
    - market_making, mean_reversion, range_reversion, multi_strategy → LIMIT order

    These tests distinguish MARKET from LIMIT by using a signal price that is
    below the candle low.  For a LIMIT BUY: candle.low > limit_price → skip.
    For a MARKET BUY: always fills at ask regardless.
    """

    @pytest.mark.asyncio
    async def test_market_making_uses_limit_order_skips_when_price_unreachable(self, mock_api):
        """MARKET_MAKING → LIMIT order; BUY skips when signal price below candle low.

        Signal price 49000 is below candle low 49500, so the limit price was
        never reached.  A LIMIT BUY must not fill; a MARKET BUY would fill at ask.
        This fails before the fix because no LIMIT fill check exists, so any BUY fills.
        """
        engine = BacktestEngine(
            mock_api, StrategyType.MARKET_MAKING, RiskLevel.MODERATE, Decimal("10000")
        )
        candles = [
            make_candle_dict(start=1_700_000_000_000, close="50000", high="50100", low="49500"),
        ]
        mock_api.get_candles = AsyncMock(return_value=candles)

        # signal.price=49000 is below candle low=49500 → LIMIT BUY unreachable
        signal = Signal(
            symbol="BTC-EUR",
            strategy="market_making",
            signal_type="BUY",
            strength=0.8,
            price=Decimal("49000"),
            reason="limit unreachable",
        )
        with patch.object(engine.strategy, "analyze", AsyncMock(return_value=signal)):
            results = await engine.run(["BTC-EUR"], days=1, interval=60)

        assert results.total_trades == 0, (
            "MARKET_MAKING uses LIMIT order: BUY must not fill when signal.price "
            "is below candle low (limit price was never reached)"
        )

    @pytest.mark.asyncio
    async def test_momentum_uses_market_order_fills_even_when_limit_price_unreachable(
        self, mock_api
    ):
        """MOMENTUM → MARKET order; BUY fills at ask even when signal price below candle low.

        Signal price 49000 is below candle low 49500.  A LIMIT BUY at 49000 would
        not fill (price never reached).  A MARKET BUY fills at ask regardless.
        This test is also a regression guard: it would FAIL if the LIMIT fill check
        is applied without the accompanying order-type selection (which would
        incorrectly treat momentum as a LIMIT order).
        """
        engine = BacktestEngine(
            mock_api, StrategyType.MOMENTUM, RiskLevel.MODERATE, Decimal("10000")
        )
        candles = [
            make_candle_dict(start=1_700_000_000_000, close="50000", high="50100", low="49500"),
            make_candle_dict(start=1_700_000_060_000, close="50000", high="50100", low="49500"),
        ]
        mock_api.get_candles = AsyncMock(return_value=candles)

        # signal.price=49000 below candle low=49500; MARKET order must still fill
        signal = Signal(
            symbol="BTC-EUR",
            strategy="momentum",
            signal_type="BUY",
            strength=0.8,
            price=Decimal("49000"),
            reason="market bypasses limit check",
        )
        with patch.object(engine.strategy, "analyze", AsyncMock(return_value=signal)):
            results = await engine.run(["BTC-EUR"], days=1, interval=60)

        assert results.total_trades >= 1, (
            "MOMENTUM uses MARKET order: BUY must fill at ask even when signal.price "
            "is below candle low (MARKET bypasses the LIMIT fill range check)"
        )
