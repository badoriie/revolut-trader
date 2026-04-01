#!/usr/bin/env python3
"""
Telegram Control Plane — always-on process that owns the Telegram polling loop.

Start this process once and control the trading bot entirely via Telegram commands:
  /run [strategy] [risk] [pairs,...]  — start the trading bot
  /stop                               — stop the trading bot gracefully
  /status                             — bot status and session P&L
  /balance                            — cash balance and open positions
  /report [days]                      — analytics report (default 30 days)
  /help                               — list all commands

The control plane never exits on its own; stop it with Ctrl-C or SIGTERM.
"""

import asyncio
import contextlib
import os
import signal
import sys
from decimal import Decimal

from loguru import logger

from src.bot import TradingBot
from src.config import RiskLevel, StrategyType, settings
from src.utils.db_persistence import DatabasePersistence
from src.utils.telegram import TelegramNotifier


class TelegramControlPlane:
    """Always-on Telegram command dispatcher.

    Owns the single Telegram polling loop.  When the trading bot is started via
    /run, it is told to skip its own listener (start_command_listener=False) so
    only one consumer reads each update.
    """

    def __init__(self) -> None:
        self.notifier = TelegramNotifier(
            token=settings.telegram_bot_token or "",
            chat_id=settings.telegram_chat_id or "",
        )
        self.persistence = DatabasePersistence()
        self.bot = None
        self._bot_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Send a startup message and begin polling for Telegram commands."""
        await self.notifier.reply("🤖 Telegram Control Plane started. Type /help for commands.")
        await self.notifier.start_polling(self._handle_command, self._stop_event)

    def shutdown(self) -> None:
        """Signal the polling loop to exit."""
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    async def _handle_command(self, command: str, args: list[str]) -> None:
        """Dispatch an incoming Telegram command to the appropriate handler.

        Args:
            command: The command name without the leading slash (e.g. ``"run"``).
            args:    Any whitespace-separated tokens that followed the command.
        """
        dispatch = {
            "start": self._cmd_help,
            "help": self._cmd_help,
            "run": lambda: self._cmd_run(args),
            "stop": self._cmd_stop,
            "status": self._cmd_status,
            "balance": self._cmd_balance,
            "report": lambda: self._cmd_report(int(args[0]) if args else 30),
        }
        handler = dispatch.get(command)
        if handler is None:
            await self.notifier.reply(
                f"Unknown command: /{command}\nType /help for available commands."
            )
            return
        await handler()

    # ------------------------------------------------------------------
    # /help
    # ------------------------------------------------------------------

    async def _cmd_help(self) -> None:
        """Send the list of available commands."""
        msg = (
            "🤖 *Revolut Trader Control Plane*\n\n"
            "/run \\[strategy\\] \\[risk\\] \\[pairs,...\\] — start the trading bot\n"
            "/stop — stop the trading bot\n"
            "/status — bot status and P&L\n"
            "/balance — cash balance and positions\n"
            "/report \\[days\\] — analytics report \\(default 30\\)\n"
            "/help — this message"
        )
        await self.notifier.reply(msg)

    # ------------------------------------------------------------------
    # /run
    # ------------------------------------------------------------------

    async def _cmd_run(self, args: list[str]) -> None:
        """Start the trading bot from Telegram.

        Parses optional positional args: strategy name, risk level, or
        comma-separated pairs.  Any unrecognised token is silently ignored.

        Args:
            args: Tokens following /run in the Telegram message.
        """
        # If a task exists and has not finished, the bot is still running.
        if self._bot_task is not None and not self._bot_task.done():
            await self.notifier.reply("⚠️ Bot is already running. Use /stop first.")
            return

        # Parse optional positional args.
        strategy_type: StrategyType | None = None
        risk_level: RiskLevel | None = None
        trading_pairs: list[str] | None = None

        for token in args:
            token_lower = token.lower()
            if token_lower in StrategyType._value2member_map_:
                strategy_type = StrategyType(token_lower)
            elif token_lower in RiskLevel._value2member_map_:
                risk_level = RiskLevel(token_lower)
            elif "," in token or token.isupper():
                # Treat as comma-separated pairs list or single pair (e.g. BTC-EUR).
                trading_pairs = token.split(",")

        try:
            self.bot = TradingBot(
                strategy_type=strategy_type,
                risk_level=risk_level,
                trading_pairs=trading_pairs,
            )
            await self.bot.start(start_command_listener=False)
        except Exception as exc:
            logger.error(f"Bot start failed: {exc}")
            await self.notifier.reply(f"❌ Failed to start bot: {exc}")
            self.bot = None
            return

        self._bot_task = asyncio.create_task(self._run_bot())
        await self.notifier.reply("✅ Trading bot started.\nType /status to check progress.")

    async def _run_bot(self) -> None:
        """Wrap the trading loop so bot.stop() is always called on exit.

        This coroutine is run as a background task.  Whether the loop exits
        cleanly, raises an exception, or is cancelled, the finally block
        ensures the bot is fully shut down (orders cancelled, positions
        closed, DB saved).
        """
        assert self.bot is not None
        try:
            await self.bot.run_trading_loop()
        except asyncio.CancelledError:
            # Re-raise immediately; finally block will still execute before propagation
            raise
        except Exception as exc:
            logger.error(f"Trading loop crashed: {exc}", exc_info=True)
            with contextlib.suppress(Exception):
                await self.notifier.reply(f"❌ Trading bot crashed: {exc}")
        finally:
            if self.bot is not None and self.bot.is_running:
                await self.bot.stop()
            self.bot = None
            self._bot_task = None

    # ------------------------------------------------------------------
    # /stop
    # ------------------------------------------------------------------

    async def _cmd_stop(self) -> None:
        """Stop the running trading bot gracefully."""
        if self._bot_task is None or self._bot_task.done():
            await self.notifier.reply("⚠️ Bot is not running.")
            return

        assert self.bot is not None
        await self.notifier.reply("⏳ Stopping trading bot…")

        # Signal the trading loop to exit; _run_bot's finally block calls bot.stop().
        self.bot.is_running = False
        await self._bot_task
        self.bot = None
        self._bot_task = None

        await self.notifier.reply("🛑 Trading bot stopped.")

    # ------------------------------------------------------------------
    # /status
    # ------------------------------------------------------------------

    async def _cmd_status(self) -> None:
        """Report bot status.  Delegates to the bot when running."""
        if self._bot_task is None or self._bot_task.done():
            await self.notifier.reply("🔴 Bot is not running. Use /run to start it.")
            return
        assert self.bot is not None
        await self.bot._cmd_status()

    # ------------------------------------------------------------------
    # /balance
    # ------------------------------------------------------------------

    async def _cmd_balance(self) -> None:
        """Report account balance.  Delegates to the bot when running."""
        if self._bot_task is None or self._bot_task.done():
            await self.notifier.reply("🔴 Bot is not running. Use /run to start it.")
            return
        assert self.bot is not None
        await self.bot._cmd_balance()

    # ------------------------------------------------------------------
    # /report
    # ------------------------------------------------------------------

    async def _cmd_report(self, days: int) -> None:
        """Send an analytics report.

        Delegates to the bot when running (so it includes the live session).
        Falls back to a direct database query when the bot is idle.

        Args:
            days: Number of historical days to include in the report.
        """
        if self._bot_task is not None and not self._bot_task.done():
            assert self.bot is not None
            await self.bot._cmd_report(days)
            return

        # Bot is not running — query the database directly.
        try:
            analytics = self.persistence.get_analytics(days=days)
        except Exception as exc:
            logger.error(f"Failed to query analytics: {exc}")
            await self.notifier.reply(f"❌ Could not fetch report: {exc}")
            return

        total_trades = analytics.get("total_trades", 0)
        if not total_trades:
            await self.notifier.reply(f"📊 No trade data found for the last {days} days.")
            return

        await self.notifier.notify_report_ready(
            days=days,
            total_trades=total_trades,
            total_pnl=Decimal(str(analytics.get("total_pnl", 0))),
            return_pct=float(analytics.get("return_pct", 0.0)),
            win_rate=float(analytics.get("win_rate", 0.0)),
            sharpe_ratio=float(analytics.get("sharpe_ratio") or 0.0),
            max_drawdown_pct=float(analytics.get("max_drawdown_pct", 0.0)),
            report_path="(run `revt db report` for full PDF)",
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_control_plane() -> None:
    """Start the Telegram Control Plane process.

    Checks that Telegram credentials are configured, sets up signal handlers
    for clean shutdown, and runs the async event loop until interrupted.
    """
    # Validate Telegram configuration before doing anything else.
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.error(
            "Telegram is not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
            "via 1Password:\n"
            "  make opconfig-set KEY=TELEGRAM_BOT_TOKEN VALUE=<token> ENV=dev\n"
            "  make opconfig-set KEY=TELEGRAM_CHAT_ID  VALUE=<chat_id> ENV=dev"
        )
        sys.exit(1)

    plane = TelegramControlPlane()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _handle_signal(signum: int, frame: object) -> None:
        logger.info(f"Received signal {signum}, shutting down…")
        plane.shutdown()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        loop.run_until_complete(plane.run())
    finally:
        loop.close()
    logger.info("Telegram Control Plane exited.")


if __name__ == "__main__":
    # Set ENVIRONMENT from CLI arg --env before Settings singleton is created.
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--env" and i < len(sys.argv):
            os.environ["ENVIRONMENT"] = sys.argv[i + 1]
        elif arg.startswith("--env="):
            os.environ["ENVIRONMENT"] = arg.split("=", 1)[1]

    run_control_plane()
