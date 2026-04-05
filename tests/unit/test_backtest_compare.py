"""Unit tests for cli/backtest_compare.py — strategy comparison CLI."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cli.commands.backtest_compare import (
    ALL_RISK_LEVELS,
    ALL_STRATEGIES,
    _persist_result,
    _print_comparison_table,
    main,
    run_compare,
    run_compare_cli,
    setup_logging,
)
from src.backtest.engine import BacktestResults
from src.config import RiskLevel, StrategyType


def _make_asyncio_run_mock(exc=None):
    """Return a side_effect for asyncio.run that closes the coroutine before optionally raising."""

    def _handler(coro):
        if hasattr(coro, "close"):
            coro.close()
        if exc is not None:
            raise exc

    return _handler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    # We need trades for the profit_factor property, but since we mock
    # results usage in _persist_result via direct attribute access we can
    # also add synthetic trades to get the desired profit_factor.
    if winning_trades > 0 and losing_trades > 0:
        r.trades = [
            {"pnl": profit_factor * 100, "side": "buy"},
            {"pnl": -100, "side": "sell"},
        ]
    elif winning_trades > 0:
        r.trades = [{"pnl": 100, "side": "buy"}]
    return r


def _make_row(
    *,
    strategy: str = "momentum",
    risk_level: str = "conservative",
    return_pct: float = 5.0,
    total_pnl: float = 500.0,
    total_fees: float = 9.45,
    total_trades: int = 12,
    winning_trades: int = 8,
    losing_trades: int = 4,
    win_rate: float = 66.7,
    profit_factor: float = 2.1,
    max_drawdown: float = 150.0,
    sharpe_ratio: float = 1.35,
    db_id: int = 1,
) -> dict:
    """Build a comparison row dict."""
    return {
        "strategy": strategy,
        "risk_level": risk_level,
        "return_pct": return_pct,
        "total_pnl": total_pnl,
        "total_fees": total_fees,
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe_ratio,
        "db_id": db_id,
    }


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


class TestSetupLogging:
    """Tests for setup_logging function."""

    @patch("cli.commands.backtest_compare.logger")
    def test_removes_existing_handlers(self, mock_logger: MagicMock) -> None:
        """setup_logging removes previous loguru handlers."""
        setup_logging("INFO")
        mock_logger.remove.assert_called_once()

    @patch("cli.commands.backtest_compare.logger")
    def test_adds_stderr_handler(self, mock_logger: MagicMock) -> None:
        """setup_logging adds a stderr handler at the requested level."""
        setup_logging("DEBUG")
        mock_logger.add.assert_called_once()
        call_kwargs = mock_logger.add.call_args
        assert call_kwargs[1]["level"] == "DEBUG" or call_kwargs[0][1:] == ()

    @patch("cli.commands.backtest_compare.logger")
    def test_warning_level(self, mock_logger: MagicMock) -> None:
        """setup_logging respects the WARNING level."""
        setup_logging("WARNING")
        _, kwargs = mock_logger.add.call_args
        assert kwargs["level"] == "WARNING"


# ---------------------------------------------------------------------------
# _persist_result
# ---------------------------------------------------------------------------


class TestPersistResult:
    """Tests for _persist_result database persistence helper."""

    def test_saves_correct_dict_to_db(self) -> None:
        """_persist_result maps BacktestResults fields to a flat dict."""
        db = MagicMock()
        db.save_backtest_run.return_value = 42

        results = _make_results()
        run_id = _persist_result(
            db=db,
            strategy="momentum",
            risk_level="conservative",
            symbols=["BTC-EUR", "ETH-EUR"],
            days=30,
            interval=60,
            initial_capital=Decimal("10000"),
            results=results,
        )

        assert run_id == 42
        db.save_backtest_run.assert_called_once()
        call_kwargs = db.save_backtest_run.call_args[1]
        assert call_kwargs["strategy"] == "momentum"
        assert call_kwargs["risk_level"] == "conservative"
        assert call_kwargs["symbols"] == ["BTC-EUR", "ETH-EUR"]
        assert call_kwargs["days"] == 30
        assert call_kwargs["interval"] == "60"
        assert call_kwargs["initial_capital"] == Decimal("10000")

        results_dict = call_kwargs["results"]
        assert results_dict["final_capital"] == float(Decimal("10500"))
        assert results_dict["total_pnl"] == float(Decimal("500"))
        assert results_dict["total_fees"] == float(Decimal("9.45"))
        assert results_dict["total_trades"] == 12
        assert results_dict["winning_trades"] == 8
        assert results_dict["losing_trades"] == 4
        assert results_dict["max_drawdown"] == float(Decimal("150"))
        assert results_dict["sharpe_ratio"] == 1.35

    def test_returns_db_primary_key(self) -> None:
        """_persist_result returns the integer PK from the DB layer."""
        db = MagicMock()
        db.save_backtest_run.return_value = 99

        results = _make_results()
        assert (
            _persist_result(
                db=db,
                strategy="breakout",
                risk_level="aggressive",
                symbols=["BTC-EUR"],
                days=7,
                interval=15,
                initial_capital=Decimal("5000"),
                results=results,
            )
            == 99
        )


# ---------------------------------------------------------------------------
# _print_comparison_table
# ---------------------------------------------------------------------------


class TestPrintComparisonTable:
    """Tests for _print_comparison_table output formatting."""

    def test_empty_rows(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Empty input prints a 'no results' message."""
        _print_comparison_table([])
        captured = capsys.readouterr()
        assert "No results to display." in captured.out

    def test_single_row(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Single row prints header, data line, and summary."""
        row = _make_row()
        _print_comparison_table([row])
        out = capsys.readouterr().out
        assert "STRATEGY COMPARISON" in out
        assert "momentum" in out
        assert "conservative" in out
        assert "Best:" in out
        assert "Worst:" in out
        assert "Avg return:" in out

    def test_multiple_rows_sorted_by_return(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Multiple rows are sorted by return_pct descending."""
        rows = [
            _make_row(strategy="mean_reversion", return_pct=-2.0),
            _make_row(strategy="momentum", return_pct=5.0),
            _make_row(strategy="breakout", return_pct=3.0),
        ]
        _print_comparison_table(rows)
        out = capsys.readouterr().out
        lines = out.strip().split("\n")
        # Data lines start with a rank number followed by a strategy name
        data_lines = [
            line
            for line in lines
            if line.strip() and line.strip()[0].isdigit() and "conservative" in line
        ]
        assert len(data_lines) == 3
        # First data line should be the best (momentum, 5.0%)
        assert "momentum" in data_lines[0]
        # Last data line should be the worst (mean_reversion, -2.0%)
        assert "mean_reversion" in data_lines[2]

    def test_inf_profit_factor(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Infinite profit factor is displayed as 'inf'."""
        row = _make_row(profit_factor=float("inf"))
        _print_comparison_table([row])
        out = capsys.readouterr().out
        assert "inf" in out

    def test_negative_pnl_formatting(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Negative P&L uses minus sign in output."""
        row = _make_row(total_pnl=-200.0, return_pct=-2.0)
        _print_comparison_table([row])
        out = capsys.readouterr().out
        # Negative net P&L should have a minus symbol
        assert "-\u20ac" in out or "-€" in out

    def test_custom_currency_symbol(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Custom currency symbol is used in output."""
        row = _make_row()
        _print_comparison_table([row], currency_symbol="$")
        out = capsys.readouterr().out
        assert "$" in out

    def test_summary_best_and_worst(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Summary correctly identifies best and worst strategies."""
        rows = [
            _make_row(strategy="momentum", return_pct=10.0, risk_level="aggressive"),
            _make_row(strategy="breakout", return_pct=-5.0, risk_level="conservative"),
        ]
        _print_comparison_table(rows)
        out = capsys.readouterr().out
        assert "Best:  momentum (aggressive)" in out
        assert "Worst: breakout (conservative)" in out


# ---------------------------------------------------------------------------
# run_compare (async)
# ---------------------------------------------------------------------------


class TestRunCompare:
    """Tests for the async run_compare function."""

    @pytest.mark.asyncio
    @patch("cli.commands.backtest_compare.DatabasePersistence")
    @patch("cli.commands.backtest_compare.BacktestEngine")
    @patch("cli.commands.backtest_compare.create_api_client")
    @patch("cli.commands.backtest_compare._print_comparison_table")
    async def test_with_custom_args(
        self,
        mock_print_table: MagicMock,
        mock_create_api: MagicMock,
        mock_engine_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """run_compare with explicit strategies/risk/pairs runs the right combos."""
        # API client mock
        mock_client = AsyncMock()
        mock_create_api.return_value = mock_client

        # DB mock
        mock_db = MagicMock()
        mock_db.save_backtest_run.return_value = 1
        mock_db_cls.return_value = mock_db

        # Engine mock
        mock_engine = MagicMock()
        results = _make_results()
        mock_engine.run = AsyncMock(return_value=results)
        mock_engine_cls.return_value = mock_engine

        args = SimpleNamespace(
            strategies="momentum",
            risk="conservative",
            risk_levels=None,
            pairs="BTC-EUR",
            days=7,
            interval=15,
            capital=5000.0,
            log_level="INFO",
        )
        await run_compare(args)

        # API client lifecycle
        mock_client.initialize.assert_awaited_once()
        mock_client.close.assert_awaited_once()

        # One strategy * one risk level = one engine run
        mock_engine_cls.assert_called_once()
        mock_engine.run.assert_awaited_once()

        # Results persisted
        mock_db.save_backtest_run.assert_called_once()

        # Table printed
        mock_print_table.assert_called_once()
        rows = mock_print_table.call_args[0][0]
        assert len(rows) == 1
        assert rows[0]["strategy"] == "momentum"

    @pytest.mark.asyncio
    @patch("cli.commands.backtest_compare.DatabasePersistence")
    @patch("cli.commands.backtest_compare.BacktestEngine")
    @patch("cli.commands.backtest_compare.create_api_client")
    @patch("cli.commands.backtest_compare._print_comparison_table")
    async def test_defaults_use_all_strategies(
        self,
        mock_print_table: MagicMock,
        mock_create_api: MagicMock,
        mock_engine_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """When strategies=None, all strategies are run."""
        mock_client = AsyncMock()
        mock_create_api.return_value = mock_client

        mock_db = MagicMock()
        mock_db.save_backtest_run.return_value = 1
        mock_db_cls.return_value = mock_db

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=_make_results())
        mock_engine_cls.return_value = mock_engine

        args = SimpleNamespace(
            strategies=None,
            risk=None,
            risk_levels=None,
            pairs=None,
            days=None,
            interval=None,
            capital=None,
            log_level=None,
        )
        await run_compare(args)

        # Should run once per strategy (default risk level = single)
        assert mock_engine_cls.call_count == len(ALL_STRATEGIES)

    @pytest.mark.asyncio
    @patch("cli.commands.backtest_compare.DatabasePersistence")
    @patch("cli.commands.backtest_compare.BacktestEngine")
    @patch("cli.commands.backtest_compare.create_api_client")
    @patch("cli.commands.backtest_compare._print_comparison_table")
    async def test_multiple_risk_levels(
        self,
        mock_print_table: MagicMock,
        mock_create_api: MagicMock,
        mock_engine_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """When risk_levels is set, each strategy runs for each risk level."""
        mock_client = AsyncMock()
        mock_create_api.return_value = mock_client

        mock_db = MagicMock()
        mock_db.save_backtest_run.return_value = 1
        mock_db_cls.return_value = mock_db

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=_make_results())
        mock_engine_cls.return_value = mock_engine

        args = SimpleNamespace(
            strategies="momentum,breakout",
            risk=None,
            risk_levels="conservative,aggressive",
            pairs="BTC-EUR",
            days=30,
            interval=60,
            capital=10000.0,
            log_level=None,
        )
        await run_compare(args)

        # 2 strategies * 2 risk levels = 4 runs
        assert mock_engine_cls.call_count == 4

    @pytest.mark.asyncio
    @patch("cli.commands.backtest_compare.DatabasePersistence")
    @patch("cli.commands.backtest_compare.BacktestEngine")
    @patch("cli.commands.backtest_compare.create_api_client")
    @patch("cli.commands.backtest_compare._print_comparison_table")
    async def test_api_client_closed_on_error(
        self,
        mock_print_table: MagicMock,
        mock_create_api: MagicMock,
        mock_engine_cls: MagicMock,
        mock_db_cls: MagicMock,
    ) -> None:
        """API client is closed even when the engine raises."""
        mock_client = AsyncMock()
        mock_create_api.return_value = mock_client

        mock_db_cls.return_value = MagicMock()

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(side_effect=RuntimeError("boom"))
        mock_engine_cls.return_value = mock_engine

        args = SimpleNamespace(
            strategies="momentum",
            risk="conservative",
            risk_levels=None,
            pairs="BTC-EUR",
            days=7,
            interval=60,
            capital=10000.0,
            log_level=None,
        )
        with pytest.raises(RuntimeError, match="boom"):
            await run_compare(args)

        mock_client.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# run_compare_cli
# ---------------------------------------------------------------------------


class TestRunCompareCli:
    """Tests for the synchronous run_compare_cli wrapper."""

    @patch("cli.commands.backtest_compare.asyncio.run", side_effect=_make_asyncio_run_mock())
    @patch("cli.commands.backtest_compare.setup_logging")
    def test_success(self, mock_setup: MagicMock, mock_asyncio_run: MagicMock) -> None:
        """Successful run calls asyncio.run and setup_logging."""
        run_compare_cli(strategies="momentum", days=7)
        mock_setup.assert_called_once()
        mock_asyncio_run.assert_called_once()

    @patch(
        "cli.commands.backtest_compare.asyncio.run",
        side_effect=_make_asyncio_run_mock(KeyboardInterrupt()),
    )
    @patch("cli.commands.backtest_compare.setup_logging")
    def test_keyboard_interrupt(self, mock_setup: MagicMock, mock_asyncio_run: MagicMock) -> None:
        """KeyboardInterrupt is caught gracefully (no sys.exit)."""
        # Should NOT raise
        run_compare_cli(strategies="momentum")

    @patch(
        "cli.commands.backtest_compare.asyncio.run",
        side_effect=_make_asyncio_run_mock(ValueError("bad config")),
    )
    @patch("cli.commands.backtest_compare.setup_logging")
    def test_exception_exits(self, mock_setup: MagicMock, mock_asyncio_run: MagicMock) -> None:
        """Unhandled exception triggers sys.exit(1)."""
        with pytest.raises(SystemExit) as exc_info:
            run_compare_cli(strategies="momentum")
        assert exc_info.value.code == 1

    @patch("cli.commands.backtest_compare.asyncio.run", side_effect=_make_asyncio_run_mock())
    @patch("cli.commands.backtest_compare.setup_logging")
    def test_default_log_level_from_settings(
        self, mock_setup: MagicMock, mock_asyncio_run: MagicMock
    ) -> None:
        """When log_level is None, setup_logging uses settings.log_level."""
        run_compare_cli(log_level=None)
        # setup_logging is called with settings.log_level (a string)
        call_arg = mock_setup.call_args[0][0]
        assert isinstance(call_arg, str)

    @patch("cli.commands.backtest_compare.asyncio.run", side_effect=_make_asyncio_run_mock())
    @patch("cli.commands.backtest_compare.setup_logging")
    def test_explicit_log_level(self, mock_setup: MagicMock, mock_asyncio_run: MagicMock) -> None:
        """Explicit log_level is forwarded to setup_logging."""
        run_compare_cli(log_level="DEBUG")
        mock_setup.assert_called_once_with("DEBUG")


# ---------------------------------------------------------------------------
# main (argparse entry point)
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for the main() CLI entry point."""

    @patch("cli.commands.backtest_compare.run_compare_cli")
    def test_default_args(self, mock_cli: MagicMock) -> None:
        """main() with no CLI args dispatches to run_compare_cli with defaults."""
        with patch("sys.argv", ["backtest_compare"]):
            main()
        mock_cli.assert_called_once_with(
            strategies=None,
            risk=None,
            risk_levels=None,
            pairs=None,
            days=None,
            interval=None,
            capital=None,
            log_level=None,
        )

    @patch("cli.commands.backtest_compare.run_compare_cli")
    def test_custom_args(self, mock_cli: MagicMock) -> None:
        """main() forwards parsed flags to run_compare_cli."""
        with patch(
            "sys.argv",
            [
                "backtest_compare",
                "--strategies",
                "momentum,breakout",
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
        mock_cli.assert_called_once_with(
            strategies="momentum,breakout",
            risk="aggressive",
            risk_levels=None,
            pairs="BTC-EUR",
            days=14,
            interval=60,
            capital=5000.0,
            log_level="DEBUG",
        )

    @patch("cli.commands.backtest_compare.run_compare_cli")
    def test_risk_levels_flag(self, mock_cli: MagicMock) -> None:
        """main() passes --risk-levels to run_compare_cli."""
        with patch(
            "sys.argv",
            ["backtest_compare", "--risk-levels", "conservative,aggressive"],
        ):
            main()
        call_kwargs = mock_cli.call_args[1]
        assert call_kwargs["risk_levels"] == "conservative,aggressive"


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    """Verify module-level constant lists."""

    def test_all_strategies_contains_known_values(self) -> None:
        """ALL_STRATEGIES matches the StrategyType enum members."""
        assert set(ALL_STRATEGIES) == {s.value for s in StrategyType}

    def test_all_risk_levels_contains_known_values(self) -> None:
        """ALL_RISK_LEVELS matches the RiskLevel enum members."""
        assert set(ALL_RISK_LEVELS) == {r.value for r in RiskLevel}
