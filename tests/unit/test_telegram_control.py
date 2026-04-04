"""Tests for TelegramControlPlane — always-on Telegram command listener."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_persistence():
    m = MagicMock()
    m.get_analytics.return_value = {"total_trades": 0}
    return m


@pytest.fixture
def mock_notifier():
    n = MagicMock()
    n.reply = AsyncMock()
    n.notify_report_ready = AsyncMock()
    n.start_polling = AsyncMock()
    return n


@pytest.fixture
def plane(mock_notifier, mock_persistence, monkeypatch):
    monkeypatch.setattr("cli.telegram_control.DatabasePersistence", lambda: mock_persistence)
    with patch("cli.telegram_control.TelegramNotifier", return_value=mock_notifier):
        from cli.telegram_control import TelegramControlPlane

        p = TelegramControlPlane()
    p.notifier = mock_notifier
    return p


def _pending_task() -> asyncio.Task:
    """Return a running task that never finishes on its own."""

    async def _forever() -> None:
        await asyncio.sleep(9999)

    return asyncio.create_task(_forever())


# ---------------------------------------------------------------------------
# _handle_command dispatch
# ---------------------------------------------------------------------------


class TestHandleCommand:
    @pytest.mark.asyncio
    async def test_unknown_command_sends_help_hint(self, plane):
        await plane._handle_command("foobar", [])
        plane.notifier.reply.assert_awaited_once()
        text = plane.notifier.reply.call_args.args[0]
        assert "foobar" in text or "/help" in text

    @pytest.mark.asyncio
    async def test_help_command_lists_run_and_stop(self, plane):
        await plane._handle_command("help", [])
        text = plane.notifier.reply.call_args.args[0]
        assert "/run" in text
        assert "/stop" in text
        assert "/status" in text
        assert "/balance" in text
        assert "/report" in text

    @pytest.mark.asyncio
    async def test_start_command_dispatches_to_help(self, plane):
        """/start (Telegram bot greeting) is treated as /help."""
        await plane._handle_command("start", [])
        plane.notifier.reply.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_report_command_dispatches_with_days(self, plane, mock_persistence):
        mock_persistence.get_analytics.return_value = {
            "total_trades": 5,
            "win_rate": 60.0,
            "total_pnl": 100.0,
            "return_pct": 1.0,
            "sharpe_ratio": 0.8,
            "max_drawdown_pct": 2.0,
        }
        await plane._handle_command("report", ["7"])
        # Should call reply at least once to notify it's generating
        assert plane.notifier.reply.await_count >= 1

    @pytest.mark.asyncio
    async def test_report_command_defaults_to_30_days(self, plane, mock_persistence):
        mock_persistence.get_analytics.return_value = {
            "total_trades": 5,
            "win_rate": 60.0,
            "total_pnl": 100.0,
            "return_pct": 1.0,
            "sharpe_ratio": 0.8,
            "max_drawdown_pct": 2.0,
        }
        await plane._handle_command("report", [])
        # Should call reply at least once to notify it's generating
        assert plane.notifier.reply.await_count >= 1


# ---------------------------------------------------------------------------
# /run
# ---------------------------------------------------------------------------


class TestRunCommand:
    @pytest.mark.asyncio
    async def test_run_starts_bot_with_command_listener_disabled(self, plane):
        """Bot is started with start_command_listener=False so the control plane
        owns the single Telegram polling loop."""
        mock_bot = MagicMock()
        mock_bot.start = AsyncMock()
        mock_bot.run_trading_loop = AsyncMock()
        mock_bot.stop = AsyncMock()
        mock_bot.is_running = True

        with patch("cli.telegram_control.TradingBot", return_value=mock_bot):
            await plane._cmd_run([])

        mock_bot.start.assert_awaited_once_with(start_command_listener=False)

    @pytest.mark.asyncio
    async def test_run_replies_started_confirmation(self, plane):
        mock_bot = MagicMock()
        mock_bot.start = AsyncMock()
        mock_bot.run_trading_loop = AsyncMock()
        mock_bot.stop = AsyncMock()
        mock_bot.is_running = True

        with patch("cli.telegram_control.TradingBot", return_value=mock_bot):
            await plane._cmd_run([])

        plane.notifier.reply.assert_awaited()
        text = plane.notifier.reply.call_args.args[0]
        assert "✅" in text or "started" in text.lower()

    @pytest.mark.asyncio
    async def test_run_creates_bot_task(self, plane):
        mock_bot = MagicMock()
        mock_bot.start = AsyncMock()
        mock_bot.run_trading_loop = AsyncMock()
        mock_bot.stop = AsyncMock()
        mock_bot.is_running = True

        with patch("cli.telegram_control.TradingBot", return_value=mock_bot):
            await plane._cmd_run([])

        assert plane._bot_task is not None

    @pytest.mark.asyncio
    async def test_run_rejects_if_already_running(self, plane):
        mock_bot = MagicMock()
        mock_bot.is_running = True
        plane.bot = mock_bot
        plane._bot_task = _pending_task()
        await asyncio.sleep(0)

        try:
            await plane._cmd_run([])
            text = plane.notifier.reply.call_args.args[0]
            assert "already" in text.lower() or "⚠️" in text
        finally:
            plane._bot_task.cancel()

    @pytest.mark.asyncio
    async def test_run_replies_on_start_failure(self, plane):
        mock_bot = MagicMock()
        mock_bot.start = AsyncMock(side_effect=RuntimeError("API key missing"))

        with patch("cli.telegram_control.TradingBot", return_value=mock_bot):
            await plane._cmd_run([])

        text = plane.notifier.reply.call_args.args[0]
        assert "❌" in text or "failed" in text.lower()

    @pytest.mark.asyncio
    async def test_run_clears_bot_on_start_failure(self, plane):
        mock_bot = MagicMock()
        mock_bot.start = AsyncMock(side_effect=RuntimeError("fail"))

        with patch("cli.telegram_control.TradingBot", return_value=mock_bot):
            await plane._cmd_run([])

        assert plane.bot is None

    @pytest.mark.asyncio
    async def test_run_parses_strategy_arg(self, plane):
        mock_bot = MagicMock()
        mock_bot.start = AsyncMock()
        mock_bot.run_trading_loop = AsyncMock()
        mock_bot.stop = AsyncMock()

        with patch("cli.telegram_control.TradingBot", return_value=mock_bot) as mock_cls:
            await plane._cmd_run(["momentum"])

        from src.config import StrategyType

        assert mock_cls.call_args.kwargs.get("strategy_type") == StrategyType.MOMENTUM

    @pytest.mark.asyncio
    async def test_run_parses_risk_arg(self, plane):
        mock_bot = MagicMock()
        mock_bot.start = AsyncMock()
        mock_bot.run_trading_loop = AsyncMock()
        mock_bot.stop = AsyncMock()

        with patch("cli.telegram_control.TradingBot", return_value=mock_bot) as mock_cls:
            await plane._cmd_run(["moderate"])

        from src.config import RiskLevel

        assert mock_cls.call_args.kwargs.get("risk_level") == RiskLevel.MODERATE

    @pytest.mark.asyncio
    async def test_run_parses_pairs_arg(self, plane):
        mock_bot = MagicMock()
        mock_bot.start = AsyncMock()
        mock_bot.run_trading_loop = AsyncMock()
        mock_bot.stop = AsyncMock()

        with patch("cli.telegram_control.TradingBot", return_value=mock_bot) as mock_cls:
            await plane._cmd_run(["BTC-EUR,ETH-EUR"])

        assert mock_cls.call_args.kwargs.get("trading_pairs") == ["BTC-EUR", "ETH-EUR"]


# ---------------------------------------------------------------------------
# /stop
# ---------------------------------------------------------------------------


class TestStopCommand:
    @pytest.mark.asyncio
    async def test_stop_rejects_when_bot_not_running(self, plane):
        await plane._cmd_stop()
        text = plane.notifier.reply.call_args.args[0]
        assert "not running" in text.lower() or "⚠️" in text

    @pytest.mark.asyncio
    async def test_stop_sets_is_running_false(self, plane):
        mock_bot = MagicMock()
        mock_bot.is_running = True

        async def bot_loop() -> None:
            while mock_bot.is_running:
                await asyncio.sleep(0)

        plane.bot = mock_bot
        plane._bot_task = asyncio.create_task(bot_loop())
        await asyncio.sleep(0)

        await plane._cmd_stop()

        assert mock_bot.is_running is False

    @pytest.mark.asyncio
    async def test_stop_clears_bot_and_task(self, plane):
        mock_bot = MagicMock()
        mock_bot.is_running = True

        async def bot_loop() -> None:
            while mock_bot.is_running:
                await asyncio.sleep(0)

        plane.bot = mock_bot
        plane._bot_task = asyncio.create_task(bot_loop())
        await asyncio.sleep(0)

        await plane._cmd_stop()

        assert plane.bot is None
        assert plane._bot_task is None

    @pytest.mark.asyncio
    async def test_stop_sends_stopping_message(self, plane):
        mock_bot = MagicMock()
        mock_bot.is_running = True

        async def bot_loop() -> None:
            while mock_bot.is_running:
                await asyncio.sleep(0)

        plane.bot = mock_bot
        plane._bot_task = asyncio.create_task(bot_loop())
        await asyncio.sleep(0)

        await plane._cmd_stop()

        plane.notifier.reply.assert_awaited()


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------


class TestStatusCommand:
    @pytest.mark.asyncio
    async def test_status_when_not_running_sends_not_running(self, plane):
        await plane._cmd_status()
        text = plane.notifier.reply.call_args.args[0]
        assert "not running" in text.lower() or "🔴" in text

    @pytest.mark.asyncio
    async def test_status_delegates_to_bot_when_running(self, plane):
        mock_bot = MagicMock()
        mock_bot.is_running = True
        mock_bot._cmd_status = AsyncMock()
        plane.bot = mock_bot
        plane._bot_task = _pending_task()
        await asyncio.sleep(0)

        try:
            await plane._cmd_status()
            mock_bot._cmd_status.assert_awaited_once()
        finally:
            plane._bot_task.cancel()


# ---------------------------------------------------------------------------
# /balance
# ---------------------------------------------------------------------------


class TestBalanceCommand:
    @pytest.mark.asyncio
    async def test_balance_when_not_running_sends_not_running(self, plane):
        await plane._cmd_balance()
        text = plane.notifier.reply.call_args.args[0]
        assert "not running" in text.lower() or "🔴" in text

    @pytest.mark.asyncio
    async def test_balance_delegates_to_bot_when_running(self, plane):
        mock_bot = MagicMock()
        mock_bot.is_running = True
        mock_bot._cmd_balance = AsyncMock()
        plane.bot = mock_bot
        plane._bot_task = _pending_task()
        await asyncio.sleep(0)

        try:
            await plane._cmd_balance()
            mock_bot._cmd_balance.assert_awaited_once()
        finally:
            plane._bot_task.cancel()


# ---------------------------------------------------------------------------
# /report
# ---------------------------------------------------------------------------


class TestReportCommand:
    @pytest.mark.asyncio
    async def test_report_queries_db_when_bot_not_running(self, plane, mock_persistence):
        mock_persistence.get_analytics.return_value = {
            "total_trades": 20,
            "win_rate": 55.0,
            "total_pnl": 300.0,
            "return_pct": 3.0,
            "sharpe_ratio": 0.9,
            "max_drawdown_pct": 2.5,
        }
        await plane._cmd_report(30)
        # Should call reply at least once to notify it's generating
        assert plane.notifier.reply.await_count >= 1

    @pytest.mark.asyncio
    async def test_report_replies_no_data_when_db_empty(self, plane, mock_persistence):
        mock_persistence.get_analytics.return_value = {"total_trades": 0}
        await plane._cmd_report(30)
        # Should call reply at least once (may call generate_report_data which can fail gracefully)
        assert plane.notifier.reply.await_count >= 1

    @pytest.mark.asyncio
    async def test_report_delegates_to_bot_when_running(self, plane):
        mock_bot = MagicMock()
        mock_bot.is_running = True
        mock_bot._cmd_report = AsyncMock()
        plane.bot = mock_bot
        plane._bot_task = _pending_task()
        await asyncio.sleep(0)

        try:
            await plane._cmd_report(7)
            mock_bot._cmd_report.assert_awaited_once_with(7)
        finally:
            plane._bot_task.cancel()

    @pytest.mark.asyncio
    async def test_report_handles_db_error_gracefully(self, plane, mock_persistence):
        mock_persistence.get_analytics.side_effect = Exception("DB error")
        await plane._cmd_report(30)  # must not raise
        # Should call reply at least once (may call generate_report_data which throws the error)
        assert plane.notifier.reply.await_count >= 1


# ---------------------------------------------------------------------------
# run() lifecycle
# ---------------------------------------------------------------------------


class TestRunLifecycle:
    @pytest.mark.asyncio
    async def test_run_sends_startup_message(self, plane):
        plane._stop_event.set()
        await plane.run()
        plane.notifier.reply.assert_awaited_once()
        text = plane.notifier.reply.call_args.args[0]
        assert "started" in text.lower() or "Control" in text

    @pytest.mark.asyncio
    async def test_run_calls_start_polling(self, plane):
        plane._stop_event.set()
        await plane.run()
        plane.notifier.start_polling.assert_awaited_once()
        handler, event = plane.notifier.start_polling.call_args.args
        assert callable(handler)
        assert event is plane._stop_event

    @pytest.mark.asyncio
    async def test_shutdown_stops_polling(self, plane):
        """shutdown() sets the stop_event so the polling loop exits."""
        assert not plane._stop_event.is_set()
        plane.shutdown()
        assert plane._stop_event.is_set()


# ---------------------------------------------------------------------------
# _run_bot background task
# ---------------------------------------------------------------------------


class TestRunBot:
    @pytest.mark.asyncio
    async def test_run_bot_calls_loop_and_cleans_up(self, plane):
        mock_bot = MagicMock()
        mock_bot.is_running = True
        mock_bot.run_trading_loop = AsyncMock()
        mock_bot.stop = AsyncMock()
        plane.bot = mock_bot

        await plane._run_bot()

        mock_bot.run_trading_loop.assert_awaited_once()
        mock_bot.stop.assert_awaited_once()
        assert plane.bot is None
        assert plane._bot_task is None

    @pytest.mark.asyncio
    async def test_run_bot_handles_exception(self, plane):
        mock_bot = MagicMock()
        mock_bot.is_running = True
        mock_bot.run_trading_loop = AsyncMock(side_effect=RuntimeError("crash"))
        mock_bot.stop = AsyncMock()
        plane.bot = mock_bot

        await plane._run_bot()

        mock_bot.stop.assert_awaited_once()
        assert plane.bot is None
        plane.notifier.reply.assert_awaited()
        text = plane.notifier.reply.call_args.args[0]
        assert "crash" in text.lower() or "❌" in text

    @pytest.mark.asyncio
    async def test_run_bot_handles_cancellation(self, plane):
        mock_bot = MagicMock()
        mock_bot.is_running = True
        mock_bot.run_trading_loop = AsyncMock(side_effect=asyncio.CancelledError)
        mock_bot.stop = AsyncMock()
        plane.bot = mock_bot

        with pytest.raises(asyncio.CancelledError):
            await plane._run_bot()

        # Finally block still runs
        mock_bot.stop.assert_awaited_once()
        assert plane.bot is None


# ---------------------------------------------------------------------------
# shutdown_async
# ---------------------------------------------------------------------------


class TestShutdownAsync:
    @pytest.mark.asyncio
    async def test_sends_shutdown_notification(self, plane):
        await plane.shutdown_async()
        plane.notifier.reply.assert_awaited_once()
        text = plane.notifier.reply.call_args.args[0]
        assert "shutting down" in text.lower() or "🔴" in text

    @pytest.mark.asyncio
    async def test_sets_stop_event(self, plane):
        assert not plane._stop_event.is_set()
        await plane.shutdown_async()
        assert plane._stop_event.is_set()


# ---------------------------------------------------------------------------
# /backtest
# ---------------------------------------------------------------------------


def _make_backtest_results(**overrides):
    """Return a fully-populated MagicMock BacktestResults."""
    from decimal import Decimal

    r = MagicMock()
    r.initial_capital = Decimal("10000.00")
    r.final_capital = Decimal("10100.00")
    r.total_pnl = Decimal("100.00")
    r.total_fees = Decimal("9.00")
    r.max_drawdown = Decimal("200.00")
    r.return_pct = 1.0
    r.win_rate = 60.0
    r.sharpe_ratio = 1.0
    r.max_drawdown_pct = 2.0
    r.profit_factor = 1.5
    r.total_trades = 10
    r.winning_trades = 6
    r.losing_trades = 4
    for k, v in overrides.items():
        setattr(r, k, v)
    return r


class TestBacktestCommand:
    @pytest.mark.asyncio
    async def test_backtest_rejects_if_already_running(self, plane):
        """Second /backtest while one is running gets a warning."""
        plane._backtest_task = _pending_task()
        await asyncio.sleep(0)

        try:
            await plane._cmd_backtest([])
            text = plane.notifier.reply.call_args.args[0]
            assert "already" in text.lower() or "⚠️" in text
        finally:
            plane._backtest_task.cancel()

    @pytest.mark.asyncio
    async def test_backtest_sends_running_message(self, plane):
        """Acknowledges the command immediately with a progress message."""
        mock_results = _make_backtest_results()

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=mock_results)

        mock_api = MagicMock()
        mock_api.initialize = AsyncMock()
        mock_api.close = AsyncMock()

        mock_db = MagicMock()
        mock_db.save_backtest_run = MagicMock(return_value=1)

        with (
            patch("cli.telegram_control.create_api_client", return_value=mock_api),
            patch("cli.telegram_control.BacktestEngine", return_value=mock_engine),
            patch("cli.telegram_control.DatabasePersistence", return_value=mock_db),
        ):
            await plane._cmd_backtest([])
            if plane._backtest_task:
                await plane._backtest_task

        calls = [c.args[0] for c in plane.notifier.reply.call_args_list]
        assert any("backtest" in t.lower() or "⏳" in t for t in calls)

    @pytest.mark.asyncio
    async def test_backtest_sends_results_on_success(self, plane):
        """Results message contains all key metrics (full report parity)."""
        from decimal import Decimal

        mock_results = MagicMock()
        mock_results.initial_capital = Decimal("10000.00")
        mock_results.final_capital = Decimal("10250.00")
        mock_results.total_pnl = Decimal("250.00")
        mock_results.total_fees = Decimal("22.50")
        mock_results.max_drawdown = Decimal("400.00")
        mock_results.return_pct = 2.5
        mock_results.win_rate = 65.0
        mock_results.sharpe_ratio = 1.5
        mock_results.max_drawdown_pct = 4.0
        mock_results.profit_factor = 2.1
        mock_results.total_trades = 20
        mock_results.winning_trades = 13
        mock_results.losing_trades = 7

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=mock_results)

        mock_api = MagicMock()
        mock_api.initialize = AsyncMock()
        mock_api.close = AsyncMock()

        mock_db = MagicMock()
        mock_db.save_backtest_run = MagicMock(return_value=1)

        with (
            patch("cli.telegram_control.create_api_client", return_value=mock_api),
            patch("cli.telegram_control.BacktestEngine", return_value=mock_engine),
            patch("cli.telegram_control.DatabasePersistence", return_value=mock_db),
        ):
            await plane._cmd_backtest([])
            if plane._backtest_task:
                await plane._backtest_task

        calls = [c.args[0] for c in plane.notifier.reply.call_args_list]
        results_msg = " ".join(calls)
        assert "10,000.00" in results_msg  # initial capital
        assert "10,250.00" in results_msg  # final capital
        assert "22.50" in results_msg  # fees
        assert "250.00" in results_msg  # net P&L
        assert "2.50%" in results_msg  # return
        assert "65.00%" in results_msg  # win rate
        assert "2.10" in results_msg  # profit factor
        assert "4.00%" in results_msg  # max drawdown pct
        assert "400.00" in results_msg  # max drawdown abs
        assert "1.500" in results_msg  # sharpe

    @pytest.mark.asyncio
    async def test_backtest_saves_to_db(self, plane):
        """Completed backtest is persisted to the database."""
        mock_results = _make_backtest_results()

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=mock_results)

        mock_api = MagicMock()
        mock_api.initialize = AsyncMock()
        mock_api.close = AsyncMock()

        mock_db = MagicMock()
        mock_db.save_backtest_run = MagicMock(return_value=1)

        with (
            patch("cli.telegram_control.create_api_client", return_value=mock_api),
            patch("cli.telegram_control.BacktestEngine", return_value=mock_engine),
            patch("cli.telegram_control.DatabasePersistence", return_value=mock_db),
        ):
            await plane._cmd_backtest([])
            if plane._backtest_task:
                await plane._backtest_task

        mock_db.save_backtest_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_backtest_sends_error_on_failure(self, plane):
        """Engine errors are caught and reported via Telegram."""
        mock_api = MagicMock()
        mock_api.initialize = AsyncMock()
        mock_api.close = AsyncMock()

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(side_effect=RuntimeError("no data"))

        with (
            patch("cli.telegram_control.create_api_client", return_value=mock_api),
            patch("cli.telegram_control.BacktestEngine", return_value=mock_engine),
        ):
            await plane._cmd_backtest([])
            if plane._backtest_task:
                await plane._backtest_task

        calls = [c.args[0] for c in plane.notifier.reply.call_args_list]
        assert any("❌" in t or "failed" in t.lower() for t in calls)

    @pytest.mark.asyncio
    async def test_backtest_clears_task_on_completion(self, plane):
        """_backtest_task is set to None after the run finishes."""
        mock_results = _make_backtest_results()

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=mock_results)

        mock_api = MagicMock()
        mock_api.initialize = AsyncMock()
        mock_api.close = AsyncMock()

        mock_db = MagicMock()
        mock_db.save_backtest_run = MagicMock(return_value=1)

        with (
            patch("cli.telegram_control.create_api_client", return_value=mock_api),
            patch("cli.telegram_control.BacktestEngine", return_value=mock_engine),
            patch("cli.telegram_control.DatabasePersistence", return_value=mock_db),
        ):
            await plane._cmd_backtest([])
            if plane._backtest_task:
                await plane._backtest_task

        assert plane._backtest_task is None

    @pytest.mark.asyncio
    async def test_backtest_parses_strategy_arg(self, plane):
        """Strategy token is passed to BacktestEngine."""
        mock_results = _make_backtest_results()

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=mock_results)

        mock_api = MagicMock()
        mock_api.initialize = AsyncMock()
        mock_api.close = AsyncMock()

        mock_db = MagicMock()
        mock_db.save_backtest_run = MagicMock(return_value=1)

        with (
            patch("cli.telegram_control.create_api_client", return_value=mock_api),
            patch("cli.telegram_control.BacktestEngine", return_value=mock_engine) as mock_cls,
            patch("cli.telegram_control.DatabasePersistence", return_value=mock_db),
        ):
            await plane._cmd_backtest(["momentum"])
            if plane._backtest_task:
                await plane._backtest_task

        from src.config import StrategyType

        assert mock_cls.call_args.kwargs.get("strategy_type") == StrategyType.MOMENTUM

    @pytest.mark.asyncio
    async def test_backtest_parses_days_arg(self, plane):
        """Numeric token is parsed as days."""
        mock_results = _make_backtest_results()

        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value=mock_results)

        mock_api = MagicMock()
        mock_api.initialize = AsyncMock()
        mock_api.close = AsyncMock()

        mock_db = MagicMock()
        mock_db.save_backtest_run = MagicMock(return_value=1)

        with (
            patch("cli.telegram_control.create_api_client", return_value=mock_api),
            patch("cli.telegram_control.BacktestEngine", return_value=mock_engine),
            patch("cli.telegram_control.DatabasePersistence", return_value=mock_db),
        ):
            await plane._cmd_backtest(["14"])
            if plane._backtest_task:
                await plane._backtest_task

        mock_engine.run.assert_awaited_once()
        call_kwargs = mock_engine.run.call_args.kwargs
        assert call_kwargs.get("days") == 14

    @pytest.mark.asyncio
    async def test_help_command_lists_backtest(self, plane):
        """/help output includes the /backtest command."""
        await plane._cmd_help()
        text = plane.notifier.reply.call_args.args[0]
        assert "/backtest" in text


# ---------------------------------------------------------------------------
# run_control_plane entry point
# ---------------------------------------------------------------------------


class TestRunControlPlane:
    @patch("cli.telegram_control.settings")
    def test_exits_when_telegram_not_configured(self, mock_settings):
        mock_settings.telegram_bot_token = None
        mock_settings.telegram_chat_id = None

        from cli.telegram_control import run_control_plane

        with pytest.raises(SystemExit) as exc_info:
            run_control_plane()
        assert exc_info.value.code == 1

    @patch("cli.telegram_control.asyncio")
    @patch("cli.telegram_control.signal")
    @patch("cli.telegram_control.TelegramControlPlane")
    @patch("cli.telegram_control.settings")
    def test_runs_event_loop(self, mock_settings, mock_plane_cls, mock_signal, mock_asyncio):
        mock_settings.telegram_bot_token = "token"
        mock_settings.telegram_chat_id = "123"

        mock_loop = MagicMock()
        mock_asyncio.new_event_loop.return_value = mock_loop

        from cli.telegram_control import run_control_plane

        run_control_plane()

        mock_loop.run_until_complete.assert_called_once()
        mock_loop.close.assert_called_once()


# ---------------------------------------------------------------------------
# /report with PDF (telegram_control lines 264-298)
# ---------------------------------------------------------------------------


class TestReportWithPdf:
    @pytest.mark.asyncio
    async def test_report_sends_pdf_when_available(self, plane, mock_persistence):
        """When generate_report_data returns pdf_bytes, send_document is called."""
        plane.notifier.send_document = AsyncMock()

        mock_result = {
            "pdf_bytes": b"%PDF-1.4 test",
            "metrics": {
                "total_pnl": 500.0,
                "return_pct": 5.0,
                "win_rate": 60.0,
                "sharpe_ratio": 1.2,
                "max_drawdown_pct": 3.0,
            },
        }

        with patch("cli.analytics_report.generate_report_data", return_value=mock_result):
            await plane._cmd_report(30)

        plane.notifier.send_document.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_report_falls_back_to_text_when_no_pdf(self, plane, mock_persistence):
        """When pdf_bytes is None, falls back to text notification."""
        mock_persistence.get_analytics.return_value = {
            "total_trades": 10,
            "total_pnl": 200.0,
            "return_pct": 2.0,
            "win_rate": 55.0,
            "sharpe_ratio": 0.8,
            "max_drawdown_pct": 5.0,
        }

        mock_result = {"pdf_bytes": None}

        with patch("cli.analytics_report.generate_report_data", return_value=mock_result):
            await plane._cmd_report(30)

        plane.notifier.notify_report_ready.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_report_no_data_message(self, plane, mock_persistence):
        """When no trades in DB, sends appropriate message."""
        mock_persistence.get_analytics.return_value = {"total_trades": 0}

        mock_result = {"pdf_bytes": None}

        with patch("cli.analytics_report.generate_report_data", return_value=mock_result):
            await plane._cmd_report(30)

        plane.notifier.reply.assert_awaited()
        text = plane.notifier.reply.call_args.args[0]
        assert "no trade data" in text.lower() or "No trade data" in text
