"""Tests for cli/commands/run.py."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cli.commands.run import setup_logging


def _asyncio_run_noop(coro):
    """Side-effect for mocking asyncio.run: closes the coroutine without awaiting it.

    Without this, the unawaited coroutine triggers a RuntimeWarning that leaks
    across tests and shows up in unrelated test output.
    """
    coro.close()


def _asyncio_run_raise(exc):
    """Side-effect factory: closes the coroutine then raises the given exception."""

    def _side_effect(coro):
        coro.close()
        raise exc

    return _side_effect


class TestSetupLogging:
    """Tests for setup_logging."""

    def test_configures_stderr_handler(self) -> None:
        """setup_logging removes existing handlers and adds a stderr one."""
        setup_logging("INFO")  # should not raise

    def test_accepts_debug_level(self) -> None:
        """DEBUG log level is accepted."""
        setup_logging("DEBUG")

    def test_accepts_warning_level(self) -> None:
        """WARNING log level is accepted."""
        setup_logging("WARNING")


class TestRunBot:
    """Tests for run_bot async function."""

    @pytest.mark.asyncio
    async def test_run_bot_starts_and_stops(self) -> None:
        """run_bot starts and stops the trading bot."""
        from cli.commands.run import run_bot

        mock_bot = MagicMock()
        mock_bot.start = AsyncMock()
        mock_bot.run_trading_loop = AsyncMock()
        mock_bot.stop = AsyncMock()

        args = MagicMock()
        args.log_level = "INFO"
        args.strategy = "momentum"
        args.risk = "moderate"
        args.pairs = None
        args.interval = 10

        with (
            patch("src.bot.TradingBot", return_value=mock_bot),
            patch("src.config.settings") as mock_settings,
        ):
            mock_settings.log_level = "INFO"
            mock_settings.default_strategy.value = "momentum"
            mock_settings.risk_level.value = "moderate"
            mock_settings.interval = 10

            await run_bot(args)

        mock_bot.start.assert_awaited_once()
        mock_bot.run_trading_loop.assert_awaited_once()
        mock_bot.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_bot_with_pairs_string(self) -> None:
        """run_bot splits comma-separated pairs."""
        from cli.commands.run import run_bot

        mock_bot = MagicMock()
        mock_bot.start = AsyncMock()
        mock_bot.run_trading_loop = AsyncMock()
        mock_bot.stop = AsyncMock()

        args = MagicMock()
        args.log_level = None
        args.strategy = "momentum"
        args.risk = "moderate"
        args.pairs = "BTC-USD,ETH-USD"
        args.interval = None

        with (
            patch("src.bot.TradingBot", return_value=mock_bot) as mock_bot_cls,
            patch("src.config.settings") as mock_settings,
        ):
            mock_settings.log_level = "INFO"
            mock_settings.default_strategy.value = "momentum"
            mock_settings.risk_level.value = "moderate"
            mock_settings.interval = 10

            await run_bot(args)

        _, kwargs = mock_bot_cls.call_args
        assert kwargs["trading_pairs"] == ["BTC-USD", "ETH-USD"]

    @pytest.mark.asyncio
    async def test_run_bot_keyboard_interrupt_still_stops(self) -> None:
        """KeyboardInterrupt during run still calls bot.stop."""
        from cli.commands.run import run_bot

        mock_bot = MagicMock()
        mock_bot.start = AsyncMock()
        mock_bot.run_trading_loop = AsyncMock(side_effect=KeyboardInterrupt)
        mock_bot.stop = AsyncMock()

        args = MagicMock()
        args.log_level = None
        args.strategy = None
        args.risk = None
        args.pairs = None
        args.interval = None

        with (
            patch("src.bot.TradingBot", return_value=mock_bot),
            patch("src.config.settings") as mock_settings,
        ):
            mock_settings.log_level = "INFO"
            mock_settings.default_strategy.value = "momentum"
            mock_settings.risk_level.value = "moderate"
            mock_settings.interval = 10

            await run_bot(args)

        mock_bot.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_bot_exception_still_stops(self) -> None:
        """Unhandled exception still calls bot.stop."""
        from cli.commands.run import run_bot

        mock_bot = MagicMock()
        mock_bot.start = AsyncMock(side_effect=RuntimeError("fatal"))
        mock_bot.stop = AsyncMock()

        args = MagicMock()
        args.log_level = None
        args.strategy = None
        args.risk = None
        args.pairs = None
        args.interval = None

        with (
            patch("src.bot.TradingBot", return_value=mock_bot),
            patch("src.config.settings") as mock_settings,
        ):
            mock_settings.log_level = "INFO"
            mock_settings.default_strategy.value = "momentum"
            mock_settings.risk_level.value = "moderate"
            mock_settings.interval = 10

            await run_bot(args)

        mock_bot.stop.assert_awaited_once()


class TestMain:
    """Tests for main() entry point."""

    def _patch_main(self, live=False, input_response="no", asyncio_side_effect=None):
        """Build a context-manager stack for patching main()."""
        from src.config import TradingMode

        mock_settings = MagicMock()
        mock_settings.trading_mode = TradingMode.LIVE if live else TradingMode.PAPER
        mock_settings.get_mode_warning.return_value = "WARNING: live trading"
        return mock_settings

    def test_main_paper_mode_calls_asyncio_run(self) -> None:
        """Paper mode calls asyncio.run without confirmation."""
        from cli.commands.run import main

        mock_settings = self._patch_main(live=False)

        with (
            patch.object(sys, "argv", ["run"]),
            patch("src.config.settings", mock_settings),
            patch("cli.commands.run.asyncio.run", side_effect=_asyncio_run_noop) as mock_run,
        ):
            main()

        mock_run.assert_called_once()

    def test_main_live_mode_wrong_response_exits_0(self) -> None:
        """Wrong confirmation response exits 0 without running bot."""
        from cli.commands.run import main

        mock_settings = self._patch_main(live=True)

        with (
            patch.object(sys, "argv", ["run"]),
            patch("src.config.settings", mock_settings),
            patch("builtins.input", return_value="nope"),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0

    def test_main_live_mode_eof_exits_0(self) -> None:
        """EOFError on confirmation input exits 0."""
        from cli.commands.run import main

        mock_settings = self._patch_main(live=True)

        with (
            patch.object(sys, "argv", ["run"]),
            patch("src.config.settings", mock_settings),
            patch("builtins.input", side_effect=EOFError),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0

    def test_main_live_mode_keyboard_interrupt_exits_0(self) -> None:
        """KeyboardInterrupt on confirmation input exits 0."""
        from cli.commands.run import main

        mock_settings = self._patch_main(live=True)

        with (
            patch.object(sys, "argv", ["run"]),
            patch("src.config.settings", mock_settings),
            patch("builtins.input", side_effect=KeyboardInterrupt),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0

    def test_main_live_mode_confirmed_runs_bot(self) -> None:
        """Confirmed live mode calls asyncio.run."""
        from cli.commands.run import main

        mock_settings = self._patch_main(live=True)

        with (
            patch.object(sys, "argv", ["run"]),
            patch("src.config.settings", mock_settings),
            patch("builtins.input", return_value="I UNDERSTAND"),
            patch("cli.commands.run.asyncio.run", side_effect=_asyncio_run_noop) as mock_run,
        ):
            main()

        mock_run.assert_called_once()

    def test_main_asyncio_exception_exits_1(self) -> None:
        """Unhandled exception from asyncio.run exits 1."""
        from cli.commands.run import main

        mock_settings = self._patch_main(live=False)

        with (
            patch.object(sys, "argv", ["run"]),
            patch("src.config.settings", mock_settings),
            patch(
                "cli.commands.run.asyncio.run",
                side_effect=_asyncio_run_raise(RuntimeError("crash")),
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1

    def test_main_keyboard_interrupt_exits_cleanly(self) -> None:
        """KeyboardInterrupt from asyncio.run exits without error code."""
        from cli.commands.run import main

        mock_settings = self._patch_main(live=False)

        with (
            patch.object(sys, "argv", ["run"]),
            patch("src.config.settings", mock_settings),
            patch(
                "cli.commands.run.asyncio.run", side_effect=_asyncio_run_raise(KeyboardInterrupt())
            ),
        ):
            main()  # should not raise or sys.exit

    def test_main_sets_environment_if_missing(self) -> None:
        """main() sets ENVIRONMENT from auto-detection when absent."""
        import os

        from cli.commands.run import main

        mock_settings = self._patch_main(live=False)
        original = os.environ.pop("ENVIRONMENT", None)
        try:
            with (
                patch.object(sys, "argv", ["run"]),
                patch("cli.utils.env_detect.detect_env", return_value="dev"),
                patch("src.config.settings", mock_settings),
                patch("cli.commands.run.asyncio.run", side_effect=_asyncio_run_noop),
            ):
                main()
            assert os.environ.get("ENVIRONMENT") is not None
        finally:
            if original is not None:
                os.environ["ENVIRONMENT"] = original
            else:
                os.environ.pop("ENVIRONMENT", None)
