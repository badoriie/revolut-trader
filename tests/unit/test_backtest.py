"""Unit tests for cli/commands/backtest.py — single-strategy backtest CLI."""

from __future__ import annotations

import sys
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cli.commands.backtest import main, run_backtest, setup_logging
from src.backtest.engine import BacktestResults
from src.config import RiskLevel, StrategyType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_asyncio_run_mock(exc=None):
    """Return a side_effect for asyncio.run that closes the coroutine before optionally raising."""

    def _handler(coro):
        if hasattr(coro, "close"):
            coro.close()
        if exc is not None:
            raise exc

    return _handler


def _make_results(
    *,
    final_capital: str = "10500",
    total_pnl: str = "500",
    total_fees: str = "9.45",
    return_pct: float = 5.0,
    total_trades: int = 12,
    winning_trades: int = 8,
    losing_trades: int = 4,
    win_rate: float = 66.7,
    profit_factor: float = 2.1,
    max_drawdown: str = "150",
    sharpe_ratio: float = 1.35,
) -> BacktestResults:
    """Build a BacktestResults with controllable values."""
    r = BacktestResults()
    r.initial_capital = Decimal("10000")
    r.final_capital = Decimal(final_capital)
    r.total_pnl = Decimal(total_pnl)
    r.total_fees = Decimal(total_fees)
    r.total_trades = total_trades
    r.winning_trades = winning_trades
    r.losing_trades = losing_trades
    r.max_drawdown = Decimal(max_drawdown)
    r.sharpe_ratio = sharpe_ratio
    if winning_trades > 0 and losing_trades > 0:
        r.trades = [
            {"pnl": profit_factor * 100, "side": "buy"},
            {"pnl": -100, "side": "sell"},
        ]
    elif winning_trades > 0:
        r.trades = [{"pnl": 100, "side": "buy"}]
    return r


def _default_args(**overrides) -> SimpleNamespace:
    """Return a SimpleNamespace that mimics argparse output with sensible defaults."""
    defaults: dict = {
        "strategy": None,
        "risk": None,
        "pairs": None,
        "days": None,
        "interval": None,
        "capital": None,
        "log_level": None,
        "real_data": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


class TestSetupLogging:
    """Tests for setup_logging function."""

    @patch("cli.commands.backtest.logger")
    def test_removes_existing_handlers(self, mock_logger: MagicMock) -> None:
        """setup_logging removes previous loguru handlers before adding a new one."""
        setup_logging("INFO")
        mock_logger.remove.assert_called_once()

    @patch("cli.commands.backtest.logger")
    def test_adds_stderr_handler(self, mock_logger: MagicMock) -> None:
        """setup_logging adds exactly one stderr handler."""
        setup_logging("DEBUG")
        mock_logger.add.assert_called_once()

    @patch("cli.commands.backtest.logger")
    def test_handler_level_is_forwarded(self, mock_logger: MagicMock) -> None:
        """The requested log level is forwarded to the handler."""
        setup_logging("WARNING")
        _, kwargs = mock_logger.add.call_args
        assert kwargs["level"] == "WARNING"

    @patch("cli.commands.backtest.logger")
    def test_error_level(self, mock_logger: MagicMock) -> None:
        """setup_logging accepts ERROR level."""
        setup_logging("ERROR")
        _, kwargs = mock_logger.add.call_args
        assert kwargs["level"] == "ERROR"

    @patch("cli.commands.backtest.logger")
    def test_handler_targets_stderr(self, mock_logger: MagicMock) -> None:
        """The handler is added to sys.stderr."""
        setup_logging("INFO")
        positional_args = mock_logger.add.call_args[0]
        assert positional_args[0] is sys.stderr


# ---------------------------------------------------------------------------
# run_backtest (async)
# ---------------------------------------------------------------------------


class TestRunBacktest:
    """Tests for the async run_backtest coroutine."""

    @pytest.mark.asyncio
    @patch("cli.commands.backtest.DatabasePersistence")
    @patch("cli.commands.backtest.BacktestEngine")
    @patch("cli.commands.backtest.create_backtest_api_client")
    async def test_default_args_use_settings(
        self,
        mock_create_api: MagicMock,
        mock_engine_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """When all args are None, settings values are used as defaults."""
        mock_client = AsyncMock()
        mock_create_api.return_value = mock_client

        mock_db = MagicMock()
        mock_db.save_backtest_run.return_value = 1
        mock_db_cls.return_value = mock_db

        mock_engine = MagicMock()
        results = _make_results()
        mock_engine.run = AsyncMock(return_value=results)
        mock_engine_cls.return_value = mock_engine

        args = _default_args()
        await run_backtest(args)

        # API client lifecycle
        mock_client.initialize.assert_awaited_once()
        mock_client.close.assert_awaited_once()

        # Engine should have been created and run once
        mock_engine_cls.assert_called_once()
        mock_engine.run.assert_awaited_once()

        # Results should be persisted
        mock_db.save_backtest_run.assert_called_once()

    @pytest.mark.asyncio
    @patch("cli.commands.backtest.DatabasePersistence")
    @patch("cli.commands.backtest.BacktestEngine")
    @patch("cli.commands.backtest.create_backtest_api_client")
    async def test_explicit_args_override_settings(
        self,
        mock_create_api: MagicMock,
        mock_engine_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """Explicit CLI flag values override the 1Password settings defaults."""
        mock_client = AsyncMock()
        mock_create_api.return_value = mock_client

        mock_db = MagicMock()
        mock_db.save_backtest_run.return_value = 7
        mock_db_cls.return_value = mock_db

        mock_engine = MagicMock()
        results = _make_results()
        mock_engine.run = AsyncMock(return_value=results)
        mock_engine_cls.return_value = mock_engine

        args = _default_args(
            strategy="momentum",
            risk="aggressive",
            pairs="BTC-EUR,ETH-EUR",
            days=14,
            interval=15,
            capital=5000.0,
        )
        await run_backtest(args)

        # Engine must be constructed with the strategy and risk from args
        engine_call_kwargs = mock_engine_cls.call_args[1]
        assert engine_call_kwargs["strategy_type"] == StrategyType.MOMENTUM
        assert engine_call_kwargs["risk_level"] == RiskLevel.AGGRESSIVE
        assert engine_call_kwargs["initial_capital"] == Decimal("5000.0")

        # engine.run must receive the explicit days and interval
        run_call_kwargs = mock_engine.run.call_args[1]
        assert run_call_kwargs["symbols"] == ["BTC-EUR", "ETH-EUR"]
        assert run_call_kwargs["days"] == 14
        assert run_call_kwargs["interval"] == 15

    @pytest.mark.asyncio
    @patch("cli.commands.backtest.DatabasePersistence")
    @patch("cli.commands.backtest.BacktestEngine")
    @patch("cli.commands.backtest.create_backtest_api_client")
    async def test_real_data_flag_passed_through(
        self,
        mock_create_api: MagicMock,
        mock_engine_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """When real_data=True, create_backtest_api_client receives args with that flag."""
        mock_client = AsyncMock()
        mock_create_api.return_value = mock_client

        mock_db = MagicMock()
        mock_db.save_backtest_run.return_value = 2
        mock_db_cls.return_value = mock_db

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=_make_results())
        mock_engine_cls.return_value = mock_engine

        args = _default_args(real_data=True)
        await run_backtest(args)

        # The args object with real_data=True is forwarded to the client factory
        mock_create_api.assert_called_once_with(args)
        assert mock_create_api.call_args[0][0].real_data is True

    @pytest.mark.asyncio
    @patch("cli.commands.backtest.DatabasePersistence")
    @patch("cli.commands.backtest.BacktestEngine")
    @patch("cli.commands.backtest.create_backtest_api_client")
    async def test_saves_results_to_db(
        self,
        mock_create_api: MagicMock,
        mock_engine_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """run_backtest persists results via DatabasePersistence.save_backtest_run."""
        mock_client = AsyncMock()
        mock_create_api.return_value = mock_client

        mock_db = MagicMock()
        mock_db.save_backtest_run.return_value = 42
        mock_db_cls.return_value = mock_db

        mock_engine = MagicMock()
        results = _make_results(
            final_capital="11000",
            total_pnl="1000",
            total_fees="10",
            return_pct=10.0,
            total_trades=20,
            winning_trades=15,
            losing_trades=5,
            win_rate=75.0,
            profit_factor=3.0,
            max_drawdown="200",
            sharpe_ratio=1.8,
        )
        mock_engine.run = AsyncMock(return_value=results)
        mock_engine_cls.return_value = mock_engine

        args = _default_args(
            strategy="breakout",
            risk="conservative",
            pairs="BTC-EUR",
            days=7,
            interval=60,
            capital=10000.0,
        )
        await run_backtest(args)

        mock_db.save_backtest_run.assert_called_once()
        call_kwargs = mock_db.save_backtest_run.call_args[1]
        assert call_kwargs["strategy"] == "breakout"
        assert call_kwargs["risk_level"] == "conservative"
        assert call_kwargs["symbols"] == ["BTC-EUR"]
        assert call_kwargs["days"] == 7
        assert call_kwargs["interval"] == "60"
        assert call_kwargs["initial_capital"] == Decimal("10000.0")

        rd = call_kwargs["results"]
        assert rd["final_capital"] == float(Decimal("11000"))
        assert rd["total_pnl"] == float(Decimal("1000"))
        assert rd["total_fees"] == float(Decimal("10"))
        assert rd["return_pct"] == 10.0
        assert rd["total_trades"] == 20
        assert rd["winning_trades"] == 15
        assert rd["losing_trades"] == 5
        assert rd["win_rate"] == 75.0
        assert rd["max_drawdown"] == float(Decimal("200"))
        assert rd["sharpe_ratio"] == 1.8

    @pytest.mark.asyncio
    @patch("cli.commands.backtest.DatabasePersistence")
    @patch("cli.commands.backtest.BacktestEngine")
    @patch("cli.commands.backtest.create_backtest_api_client")
    async def test_api_client_closed_when_engine_raises(
        self,
        mock_create_api: MagicMock,
        mock_engine_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """api_client.close() is called in finally even when BacktestEngine.run raises."""
        mock_client = AsyncMock()
        mock_create_api.return_value = mock_client
        mock_db_cls.return_value = MagicMock()

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(side_effect=RuntimeError("engine exploded"))
        mock_engine_cls.return_value = mock_engine

        args = _default_args()
        with pytest.raises(RuntimeError, match="engine exploded"):
            await run_backtest(args)

        # Ensure close was still called despite the exception
        mock_client.close.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("cli.commands.backtest.DatabasePersistence")
    @patch("cli.commands.backtest.BacktestEngine")
    @patch("cli.commands.backtest.create_backtest_api_client")
    async def test_api_client_closed_on_success(
        self,
        mock_create_api: MagicMock,
        mock_engine_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """api_client.close() is called even on a successful run."""
        mock_client = AsyncMock()
        mock_create_api.return_value = mock_client

        mock_db = MagicMock()
        mock_db.save_backtest_run.return_value = 1
        mock_db_cls.return_value = mock_db

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=_make_results())
        mock_engine_cls.return_value = mock_engine

        args = _default_args()
        await run_backtest(args)

        mock_client.close.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("cli.commands.backtest.DatabasePersistence")
    @patch("cli.commands.backtest.BacktestEngine")
    @patch("cli.commands.backtest.create_backtest_api_client")
    async def test_multiple_pairs_split_correctly(
        self,
        mock_create_api: MagicMock,
        mock_engine_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """Comma-separated pairs string is split into a list correctly."""
        mock_client = AsyncMock()
        mock_create_api.return_value = mock_client

        mock_db = MagicMock()
        mock_db.save_backtest_run.return_value = 1
        mock_db_cls.return_value = mock_db

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=_make_results())
        mock_engine_cls.return_value = mock_engine

        args = _default_args(pairs="BTC-EUR,ETH-EUR,SOL-EUR")
        await run_backtest(args)

        run_call_kwargs = mock_engine.run.call_args[1]
        assert run_call_kwargs["symbols"] == ["BTC-EUR", "ETH-EUR", "SOL-EUR"]

    @pytest.mark.asyncio
    @patch("cli.commands.backtest.DatabasePersistence")
    @patch("cli.commands.backtest.BacktestEngine")
    @patch("cli.commands.backtest.create_backtest_api_client")
    async def test_print_summary_called(
        self,
        mock_create_api: MagicMock,
        mock_engine_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """results.print_summary() is called after a successful run."""
        mock_client = AsyncMock()
        mock_create_api.return_value = mock_client

        mock_db = MagicMock()
        mock_db.save_backtest_run.return_value = 1
        mock_db_cls.return_value = mock_db

        mock_engine = MagicMock()
        results = MagicMock(spec=BacktestResults)
        results.final_capital = Decimal("10500")
        results.total_pnl = Decimal("500")
        results.total_fees = Decimal("9.45")
        results.return_pct = 5.0
        results.total_trades = 12
        results.winning_trades = 8
        results.losing_trades = 4
        results.win_rate = 66.7
        results.profit_factor = 2.1
        results.max_drawdown = Decimal("150")
        results.sharpe_ratio = 1.35
        mock_engine.run = AsyncMock(return_value=results)
        mock_engine_cls.return_value = mock_engine

        args = _default_args()
        await run_backtest(args)

        results.print_summary.assert_called_once()

    @pytest.mark.asyncio
    @patch("cli.commands.backtest.DatabasePersistence")
    @patch("cli.commands.backtest.BacktestEngine")
    @patch("cli.commands.backtest.create_backtest_api_client")
    async def test_initial_capital_uses_decimal(
        self,
        mock_create_api: MagicMock,
        mock_engine_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """initial_capital passed to engine and DB is a Decimal, never float."""
        mock_client = AsyncMock()
        mock_create_api.return_value = mock_client

        mock_db = MagicMock()
        mock_db.save_backtest_run.return_value = 1
        mock_db_cls.return_value = mock_db

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=_make_results())
        mock_engine_cls.return_value = mock_engine

        args = _default_args(capital=7500.0)
        await run_backtest(args)

        engine_kwargs = mock_engine_cls.call_args[1]
        assert isinstance(engine_kwargs["initial_capital"], Decimal)
        assert engine_kwargs["initial_capital"] == Decimal("7500.0")

        db_kwargs = mock_db.save_backtest_run.call_args[1]
        assert isinstance(db_kwargs["initial_capital"], Decimal)


# ---------------------------------------------------------------------------
# main (argparse entry point)
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for the main() CLI entry point."""

    @patch("cli.commands.backtest.asyncio.run", side_effect=_make_asyncio_run_mock())
    @patch("cli.commands.backtest.setup_logging")
    def test_default_args_no_exception(
        self, mock_setup: MagicMock, mock_asyncio_run: MagicMock
    ) -> None:
        """main() with no CLI args runs without errors."""
        with patch("sys.argv", ["backtest"]):
            main()
        mock_setup.assert_called_once()
        mock_asyncio_run.assert_called_once()

    @patch("cli.commands.backtest.asyncio.run", side_effect=_make_asyncio_run_mock())
    @patch("cli.commands.backtest.setup_logging")
    def test_explicit_strategy_flag(
        self, mock_setup: MagicMock, mock_asyncio_run: MagicMock
    ) -> None:
        """main() parses --strategy and passes it to run_backtest."""
        with patch("sys.argv", ["backtest", "--strategy", "momentum"]):
            main()
        mock_asyncio_run.assert_called_once()

    @patch("cli.commands.backtest.asyncio.run", side_effect=_make_asyncio_run_mock())
    @patch("cli.commands.backtest.setup_logging")
    def test_all_flags_parsed(self, mock_setup: MagicMock, mock_asyncio_run: MagicMock) -> None:
        """main() correctly parses all available flags."""
        with patch(
            "sys.argv",
            [
                "backtest",
                "--strategy",
                "breakout",
                "--risk",
                "aggressive",
                "--pairs",
                "BTC-EUR",
                "--days",
                "14",
                "--interval",
                "60",
                "--capital",
                "5000",
                "--log-level",
                "DEBUG",
            ],
        ):
            main()
        mock_setup.assert_called_with("DEBUG")

    @patch(
        "cli.commands.backtest.asyncio.run",
        side_effect=_make_asyncio_run_mock(KeyboardInterrupt()),
    )
    @patch("cli.commands.backtest.setup_logging")
    def test_keyboard_interrupt_caught_gracefully(
        self, mock_setup: MagicMock, mock_asyncio_run: MagicMock
    ) -> None:
        """KeyboardInterrupt is caught and does not propagate or call sys.exit."""
        with patch("sys.argv", ["backtest"]):
            # Should NOT raise
            main()

    @patch(
        "cli.commands.backtest.asyncio.run",
        side_effect=_make_asyncio_run_mock(RuntimeError("unexpected crash")),
    )
    @patch("cli.commands.backtest.setup_logging")
    def test_unhandled_exception_exits_with_1(
        self, mock_setup: MagicMock, mock_asyncio_run: MagicMock
    ) -> None:
        """An unhandled exception triggers sys.exit(1)."""
        with patch("sys.argv", ["backtest"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 1

    @patch("cli.commands.backtest.asyncio.run", side_effect=_make_asyncio_run_mock())
    @patch("cli.commands.backtest.setup_logging")
    def test_log_level_falls_back_to_settings(
        self, mock_setup: MagicMock, mock_asyncio_run: MagicMock
    ) -> None:
        """When --log-level is omitted, settings.log_level is used."""
        with patch("sys.argv", ["backtest"]):
            main()
        call_arg = mock_setup.call_args[0][0]
        assert isinstance(call_arg, str)

    @patch("cli.commands.backtest.asyncio.run", side_effect=_make_asyncio_run_mock())
    @patch("cli.commands.backtest.setup_logging")
    def test_explicit_log_level_forwarded(
        self, mock_setup: MagicMock, mock_asyncio_run: MagicMock
    ) -> None:
        """Explicit --log-level is forwarded to setup_logging."""
        with patch("sys.argv", ["backtest", "--log-level", "ERROR"]):
            main()
        mock_setup.assert_called_with("ERROR")


# ---------------------------------------------------------------------------
# resolve_backtest_params integration via run_backtest
# ---------------------------------------------------------------------------


class TestResolveBacktestParams:
    """Verify that resolve_backtest_params logic is exercised correctly in run_backtest."""

    @pytest.mark.asyncio
    @patch("cli.commands.backtest.DatabasePersistence")
    @patch("cli.commands.backtest.BacktestEngine")
    @patch("cli.commands.backtest.create_backtest_api_client")
    async def test_pairs_none_falls_back_to_settings(
        self,
        mock_create_api: MagicMock,
        mock_engine_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """When pairs is None, settings.trading_pairs is used."""
        mock_client = AsyncMock()
        mock_create_api.return_value = mock_client

        mock_db = MagicMock()
        mock_db.save_backtest_run.return_value = 1
        mock_db_cls.return_value = mock_db

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=_make_results())
        mock_engine_cls.return_value = mock_engine

        args = _default_args(pairs=None)
        await run_backtest(args)

        run_kwargs = mock_engine.run.call_args[1]
        # Should be a non-empty list from settings
        assert isinstance(run_kwargs["symbols"], list)
        assert len(run_kwargs["symbols"]) > 0

    @pytest.mark.asyncio
    @patch("cli.commands.backtest.DatabasePersistence")
    @patch("cli.commands.backtest.BacktestEngine")
    @patch("cli.commands.backtest.create_backtest_api_client")
    async def test_capital_none_falls_back_to_settings(
        self,
        mock_create_api: MagicMock,
        mock_engine_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """When capital is None, settings.paper_initial_capital is used."""
        mock_client = AsyncMock()
        mock_create_api.return_value = mock_client

        mock_db = MagicMock()
        mock_db.save_backtest_run.return_value = 1
        mock_db_cls.return_value = mock_db

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=_make_results())
        mock_engine_cls.return_value = mock_engine

        args = _default_args(capital=None)
        await run_backtest(args)

        engine_kwargs = mock_engine_cls.call_args[1]
        assert isinstance(engine_kwargs["initial_capital"], Decimal)

    @pytest.mark.asyncio
    @patch("cli.commands.backtest.DatabasePersistence")
    @patch("cli.commands.backtest.BacktestEngine")
    @patch("cli.commands.backtest.create_backtest_api_client")
    async def test_days_none_falls_back_to_settings(
        self,
        mock_create_api: MagicMock,
        mock_engine_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """When days is None, settings.backtest_days is used."""
        mock_client = AsyncMock()
        mock_create_api.return_value = mock_client

        mock_db = MagicMock()
        mock_db.save_backtest_run.return_value = 1
        mock_db_cls.return_value = mock_db

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=_make_results())
        mock_engine_cls.return_value = mock_engine

        args = _default_args(days=None)
        await run_backtest(args)

        run_kwargs = mock_engine.run.call_args[1]
        assert isinstance(run_kwargs["days"], int)

    @pytest.mark.asyncio
    @patch("cli.commands.backtest.DatabasePersistence")
    @patch("cli.commands.backtest.BacktestEngine")
    @patch("cli.commands.backtest.create_backtest_api_client")
    async def test_interval_none_falls_back_to_settings(
        self,
        mock_create_api: MagicMock,
        mock_engine_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """When interval is None, settings.backtest_interval is used."""
        mock_client = AsyncMock()
        mock_create_api.return_value = mock_client

        mock_db = MagicMock()
        mock_db.save_backtest_run.return_value = 1
        mock_db_cls.return_value = mock_db

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=_make_results())
        mock_engine_cls.return_value = mock_engine

        args = _default_args(interval=None)
        await run_backtest(args)

        run_kwargs = mock_engine.run.call_args[1]
        assert isinstance(run_kwargs["interval"], int)
