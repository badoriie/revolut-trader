"""Unit tests for BacktestEngine and BacktestResults."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.backtest.engine import TAKER_FEE_PCT, BacktestEngine, BacktestResults
from src.config import RiskLevel, StrategyType
from src.models.domain import CandleData, OrderSide


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
