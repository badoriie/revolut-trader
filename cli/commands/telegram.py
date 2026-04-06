#!/usr/bin/env python3
"""
Telegram Control Plane — always-on process that owns the Telegram polling loop.

Start this process once and control the trading bot entirely via Telegram commands:
  /run [strategy] [risk] [pairs,...]  — start the trading bot
  /stop                               — stop the trading bot gracefully
  /status                             — bot status and session P&L
  /balance                            — cash balance and open positions
  /report [days]                      — analytics report (default 30 days)
  /backtest [strategy] [risk] [days] [pairs,...] — run a backtest
  /help                               — list all commands

The control plane never exits on its own; stop it with Ctrl-C or SIGTERM.
"""

import asyncio
import contextlib
import signal
import sys
from decimal import Decimal

from cli.utils.env_detect import set_env as _set_env

# ENVIRONMENT must be set before src.config is imported — Settings() is created
# at import time.  Environment is locked to git branch/tag or frozen binary.
_set_env()


from loguru import logger

from src.api import create_api_client
from src.backtest.engine import BacktestEngine
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
        self._backtest_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Send a startup message and begin polling for Telegram commands."""
        from cli.revt import _get_current_version_from_pyproject

        version = _get_current_version_from_pyproject()
        version_str = f" v{version}" if version else ""
        await self.notifier.reply(
            f"🤖 Telegram Control Plane{version_str} started. Type /help for commands."
        )
        await self.notifier.start_polling(self._handle_command, self._stop_event)

    async def shutdown_async(self) -> None:
        """Send shutdown notification and signal the polling loop to exit."""
        await self.notifier.reply("🔴 Telegram Control Plane is shutting down...")
        self._stop_event.set()

    def shutdown(self) -> None:
        """Signal the polling loop to exit (synchronous wrapper)."""
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
            "report": lambda: self._cmd_report(int(args[0]) if args and args[0].isdigit() else 30),
            "backtest": lambda: self._cmd_backtest(args),
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
            "🤖 <b>Revolut Trader Control Plane</b>\n\n"
            "/run [strategy] [risk] [pairs,...] — start the trading bot\n"
            "/stop — stop the trading bot\n"
            "/status — bot status and P&amp;L\n"
            "/balance — cash balance and positions\n"
            "/report [days] — analytics report (default 30)\n"
            "/backtest [strategy] [risk] [days] [pairs,...] — run a backtest\n"
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
    # /backtest
    # ------------------------------------------------------------------

    async def _cmd_backtest(self, args: list[str]) -> None:
        """Start a backtest run from Telegram.

        Parses optional positional args: strategy name, risk level, number of
        days (a bare integer), or comma-separated pairs.  Any unrecognised
        token is silently ignored.

        Only one backtest can run at a time.  The results summary is sent via
        Telegram when the run completes, and the run is persisted to the
        encrypted database.

        Args:
            args: Tokens following /backtest in the Telegram message.
        """
        if self._backtest_task is not None and not self._backtest_task.done():
            await self.notifier.reply("⚠️ A backtest is already running. Please wait.")
            return

        strategy_type: StrategyType | None = None
        risk_level: RiskLevel | None = None
        days: int | None = None
        trading_pairs: list[str] | None = None

        for token in args:
            token_lower = token.lower()
            if token_lower in StrategyType._value2member_map_:
                strategy_type = StrategyType(token_lower)
            elif token_lower in RiskLevel._value2member_map_:
                risk_level = RiskLevel(token_lower)
            elif token.isdigit():
                days = int(token)
            elif "," in token or token.isupper():
                trading_pairs = token.split(",")

        await self.notifier.reply("⏳ Running backtest…")
        self._backtest_task = asyncio.create_task(
            self._run_backtest(strategy_type, risk_level, days, trading_pairs)
        )

    async def _run_backtest(
        self,
        strategy_type: StrategyType | None,
        risk_level: RiskLevel | None,
        days: int | None,
        trading_pairs: list[str] | None,
    ) -> None:
        """Execute the backtest engine and report results via Telegram.

        Runs as a background asyncio task spawned by ``_cmd_backtest``.
        Clears ``_backtest_task`` on exit (success or failure).

        Args:
            strategy_type: Strategy to backtest, or ``None`` to use the
                1Password default.
            risk_level: Risk level to use, or ``None`` to use the 1Password
                default.
            days: Historical window in days, or ``None`` to use the 1Password
                default.
            trading_pairs: List of symbols, or ``None`` to use the 1Password
                default.
        """
        effective_strategy = strategy_type or settings.default_strategy
        effective_risk = risk_level or settings.risk_level
        effective_days = days if days is not None else settings.backtest_days
        effective_pairs = trading_pairs or settings.trading_pairs
        initial_capital = Decimal(str(settings.paper_initial_capital))

        api_client = create_api_client(settings.environment)
        await api_client.initialize()

        try:
            engine = BacktestEngine(
                api_client=api_client,
                strategy_type=effective_strategy,
                risk_level=effective_risk,
                initial_capital=initial_capital,
            )
            results = await engine.run(
                symbols=effective_pairs,
                days=effective_days,
                interval=settings.backtest_interval,
            )

            gross_pnl = results.total_pnl + results.total_fees
            gross_sign = "+" if gross_pnl >= 0 else ""
            net_sign = "+" if results.total_pnl >= 0 else ""
            profit_factor_str = (
                "∞" if results.profit_factor == float("inf") else f"{results.profit_factor:.2f}"
            )
            msg = (
                f"📊 <b>Backtest Results ({effective_days}d)</b>\n\n"
                f"Strategy: {effective_strategy.value}\n"
                f"Risk: {effective_risk.value}\n"
                f"Pairs: {', '.join(effective_pairs)}\n\n"
                f"💵 Initial Capital: €{results.initial_capital:,.2f}\n"
                f"💵 Final Capital:   €{results.final_capital:,.2f}\n\n"
                f"📈 Gross P&amp;L: {gross_sign}€{gross_pnl:,.2f}\n"
                f"💸 Total Fees:  -€{results.total_fees:,.2f}\n"
                f"💰 Net P&amp;L:   {net_sign}€{results.total_pnl:,.2f}\n"
                f"📊 Return:      {results.return_pct:.2f}%\n\n"
                f"🔄 Trades: {results.total_trades} "
                f"({results.winning_trades}W / {results.losing_trades}L)\n"
                f"✅ Win Rate:      {results.win_rate:.2f}%\n"
                f"⚖️  Profit Factor: {profit_factor_str}\n"
                f"📉 Max Drawdown: {results.max_drawdown_pct:.2f}% "
                f"(€{results.max_drawdown:,.2f})\n"
                f"📐 Sharpe Ratio: {results.sharpe_ratio:.3f}"
            )
            await self.notifier.reply(msg)

            db = DatabasePersistence()
            db.save_backtest_run(
                strategy=effective_strategy.value,
                risk_level=effective_risk.value,
                symbols=effective_pairs,
                days=effective_days,
                interval=str(settings.backtest_interval),
                initial_capital=initial_capital,
                results={
                    "final_capital": float(results.final_capital),
                    "total_pnl": float(results.total_pnl),
                    "total_fees": float(results.total_fees),
                    "return_pct": results.return_pct,
                    "total_trades": results.total_trades,
                    "winning_trades": results.winning_trades,
                    "losing_trades": results.losing_trades,
                    "win_rate": results.win_rate,
                    "profit_factor": results.profit_factor,
                    "max_drawdown": float(results.max_drawdown),
                    "sharpe_ratio": results.sharpe_ratio,
                },
            )

        except Exception as exc:
            logger.error(f"Backtest failed: {exc}", exc_info=True)
            await self.notifier.reply(f"❌ Backtest failed: {exc}")
        finally:
            await api_client.close()
            self._backtest_task = None

    # ------------------------------------------------------------------
    # /report
    # ------------------------------------------------------------------

    async def _cmd_report(self, days: int) -> None:
        """Send a comprehensive analytics report as PDF.

        Delegates to the bot when running (so it includes the live session).
        Falls back to generating a full PDF report when the bot is idle.

        Args:
            days: Number of historical days to include in the report.
        """
        if self._bot_task is not None and not self._bot_task.done():
            assert self.bot is not None
            await self.bot._cmd_report(days)
            return

        # Bot is not running — generate full PDF report
        from cli.utils.analytics_report import generate_report_data

        try:
            await self.notifier.reply(f"📊 Generating {days}-day analytics report...")

            # Generate report data and PDF (safe to call from async context)
            result = generate_report_data(
                days=days,
                output_dir=settings.data_dir / "reports",
            )

            if not result.get("pdf_bytes"):
                # Fall back to text summary if PDF generation failed
                analytics = self.persistence.get_analytics(days=days)
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
                    report_path="(fpdf2 not installed - run `revt db report` for full PDF)",
                )
                return

            # Send PDF via Telegram
            total_pnl = result["metrics"]["total_pnl"]
            pnl_sign = "+" if total_pnl >= 0 else ""
            caption = (
                f"📊 **Analytics Report - Last {days} Days**\n\n"
                f"📈 Total P&L: {pnl_sign}€{total_pnl:,.2f}\n"
                f"📉 Return: {result['metrics']['return_pct']:.2f}%\n"
                f"✅ Win Rate: {result['metrics']['win_rate']:.1f}%\n"
                f"📊 Sharpe Ratio: {result['metrics']['sharpe_ratio']:.2f}\n"
                f"📉 Max Drawdown: {result['metrics']['max_drawdown_pct']:.1f}%"
            )

            await self.notifier.send_document(
                document=result["pdf_bytes"],
                filename="analytics_report.pdf",
                caption=caption,
            )

        except Exception as exc:
            logger.error(f"Failed to generate report: {exc}", exc_info=True)
            await self.notifier.reply(f"❌ Could not generate report: {exc}")


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
        # Schedule async shutdown to send Telegram notification
        task = loop.create_task(plane.shutdown_async())
        # Store reference to avoid warning (task will complete during loop shutdown)
        _ = task

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        loop.run_until_complete(plane.run())
    finally:
        loop.close()
    logger.info("Telegram Control Plane exited.")


if __name__ == "__main__":
    run_control_plane()
