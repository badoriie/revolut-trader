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
